"""Dependency-free semantic identity for XLSX transport.

This is intentionally kept separate from the openpyxl ledger codec.  The
SharePoint transport must calculate the same identity on hosts where the
seer-finance package is not installed, and Office is allowed to rewrite ZIP
metadata without changing the workbook's visible meaning.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree


SEMANTIC_ALGORITHM = "xlsx-semantic-v1"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attrs(
    element: ElementTree.Element, *, omit: set[str] | None = None
) -> dict[str, str]:
    omitted = omit or set()
    return {
        _local_name(key): value
        for key, value in sorted(element.attrib.items())
        if _local_name(key) not in omitted
    }


def _text(element: ElementTree.Element | None) -> str:
    return "" if element is None else "".join(element.itertext())


def _xml_root(package: zipfile.ZipFile, name: str) -> ElementTree.Element:
    try:
        raw = package.read(name)
        return ElementTree.fromstring(raw)
    except KeyError as exc:
        raise ValueError(f"XLSX package is missing {name}") from exc
    except ElementTree.ParseError as exc:
        raise ValueError(f"XLSX package has invalid XML in {name}") from exc


def _relationship_targets(
    package: zipfile.ZipFile, rels_name: str, source_name: str
) -> dict[str, str]:
    try:
        root = _xml_root(package, rels_name)
    except ValueError:
        return {}
    source_parent = PurePosixPath(source_name).parent
    targets: dict[str, str] = {}
    for relation in root:
        if _local_name(relation.tag) != "Relationship":
            continue
        rel_id = relation.attrib.get("Id", "")
        target = relation.attrib.get("Target", "")
        if not rel_id or not target or relation.attrib.get("TargetMode") == "External":
            continue
        normalised = target.lstrip("/") if target.startswith("/") else str(
            source_parent / target
        )
        parts: list[str] = []
        for part in normalised.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(part)
        targets[rel_id] = "/".join(parts)
    return targets


def _shared_strings(package: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in package.namelist():
        return []
    root = _xml_root(package, "xl/sharedStrings.xml")
    return [_text(si) for si in root if _local_name(si.tag) == "si"]


def _formula_value(cell: ElementTree.Element, shared: list[str]) -> dict[str, Any]:
    cell_type = cell.attrib.get("t", "")
    value_node = next(
        (child for child in cell if _local_name(child.tag) == "v"), None
    )
    formula_node = next(
        (child for child in cell if _local_name(child.tag) == "f"), None
    )
    inline_node = next(
        (child for child in cell if _local_name(child.tag) == "is"), None
    )
    value = _text(value_node)
    if cell_type == "s" and value:
        try:
            value = shared[int(value)]
        except (ValueError, IndexError) as exc:
            raise ValueError("XLSX shared-string cell has an invalid index") from exc
    elif cell_type == "inlineStr":
        value = _text(inline_node)

    if cell_type in {"s", "inlineStr", "str"}:
        semantic_type = "string"
    elif cell_type in {"", "n"}:
        semantic_type = "number"
    else:
        semantic_type = cell_type
    result: dict[str, Any] = {
        "ref": cell.attrib.get("r", ""),
        "type": semantic_type,
        "value": value,
    }
    if formula_node is not None:
        result["formula"] = {
            "text": _text(formula_node),
            "attributes": _attrs(formula_node),
        }
    return result


def _table_semantics(package: zipfile.ZipFile, table_name: str) -> dict[str, Any]:
    root = _xml_root(package, table_name)
    result: dict[str, Any] = {"attributes": _attrs(root, omit={"id"}), "columns": []}
    auto_filter = next(
        (child for child in root if _local_name(child.tag) == "autoFilter"), None
    )
    if auto_filter is not None:
        result["auto_filter"] = _attrs(auto_filter)
    columns = next(
        (child for child in root if _local_name(child.tag) == "tableColumns"), None
    )
    if columns is not None:
        for column in columns:
            if _local_name(column.tag) != "tableColumn":
                continue
            entry: dict[str, Any] = {"attributes": _attrs(column, omit={"id"})}
            for child in column:
                name = _local_name(child.tag)
                if name in {"calculatedColumnFormula", "totalsRowFormula"}:
                    entry[name] = {
                        "text": _text(child),
                        "attributes": _attrs(child),
                    }
            result["columns"].append(entry)
    for child in root:
        if _local_name(child.tag) == "sortState":
            result["sortState"] = {
                "attributes": _attrs(child),
                "children": [
                    {
                        "name": _local_name(grandchild.tag),
                        "attributes": _attrs(grandchild),
                    }
                    for grandchild in child
                ],
            }
    return result


def _worksheet_semantics(
    package: zipfile.ZipFile,
    sheet_name: str,
    sheet_path: str,
    shared: list[str],
) -> dict[str, Any]:
    root = _xml_root(package, sheet_path)
    cells: list[dict[str, Any]] = []
    for row in root.iter():
        if _local_name(row.tag) != "row":
            continue
        for cell in row:
            if _local_name(cell.tag) != "c":
                continue
            if not any(
                _local_name(child.tag) in {"v", "f", "is"} for child in cell
            ):
                continue
            cells.append(_formula_value(cell, shared))
    cells.sort(key=lambda item: item.get("ref", ""))

    merged_ranges: list[str] = []
    merged_parent = next(
        (child for child in root if _local_name(child.tag) == "mergeCells"), None
    )
    if merged_parent is not None:
        merged_ranges = sorted(
            child.attrib.get("ref", "")
            for child in merged_parent
            if _local_name(child.tag) == "mergeCell" and child.attrib.get("ref")
        )

    worksheet_rels = str(
        PurePosixPath(sheet_path).parent
        / "_rels"
        / (PurePosixPath(sheet_path).name + ".rels")
    )
    relation_targets = _relationship_targets(package, worksheet_rels, sheet_path)
    tables: list[dict[str, Any]] = []
    table_parts = next(
        (child for child in root if _local_name(child.tag) == "tableParts"), None
    )
    if table_parts is not None:
        for table_part in table_parts:
            relation_id = (
                table_part.attrib.get(f"{{{_OFFICE_REL_NS}}}id")
                or table_part.attrib.get("id", "")
            )
            target = relation_targets.get(relation_id)
            if target:
                tables.append(_table_semantics(package, target))
    return {
        "name": sheet_name,
        "cells": cells,
        "merged_ranges": merged_ranges,
        "tables": tables,
    }


def semantic_payload(content: bytes) -> dict[str, Any]:
    """Return the versioned semantic representation of XLSX bytes."""
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise TypeError("XLSX content must be bytes")
    raw = bytes(content)
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ValueError("content is not a valid XLSX ZIP package")
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as package:
            names = set(package.namelist())
            if "xl/workbook.xml" not in names:
                raise ValueError("XLSX package is missing xl/workbook.xml")
            workbook_path = "xl/workbook.xml"
            workbook = _xml_root(package, workbook_path)
            shared = _shared_strings(package)
            workbook_rels = _relationship_targets(
                package, "xl/_rels/workbook.xml.rels", workbook_path
            )
            sheets_node = next(
                (child for child in workbook if _local_name(child.tag) == "sheets"),
                None,
            )
            if sheets_node is None:
                raise ValueError("XLSX workbook has no sheets")

            sheets: list[dict[str, Any]] = []
            for sheet in sheets_node:
                if _local_name(sheet.tag) != "sheet":
                    continue
                name = sheet.attrib.get("name", "")
                relation_id = (
                    sheet.attrib.get(f"{{{_OFFICE_REL_NS}}}id")
                    or sheet.attrib.get("id", "")
                )
                target = workbook_rels.get(relation_id)
                if not name or not target or target not in names:
                    raise ValueError("XLSX workbook has an unresolved worksheet")
                sheets.append(_worksheet_semantics(package, name, target, shared))

            defined_names: list[dict[str, Any]] = []
            defined_names_node = next(
                (
                    child
                    for child in workbook
                    if _local_name(child.tag) == "definedNames"
                ),
                None,
            )
            if defined_names_node is not None:
                for defined_name in defined_names_node:
                    if _local_name(defined_name.tag) != "definedName":
                        continue
                    defined_names.append(
                        {
                            "attributes": _attrs(defined_name),
                            "text": _text(defined_name),
                        }
                    )
            return {
                "algorithm": SEMANTIC_ALGORITHM,
                "workbook": {
                    "sheets": sheets,
                    "defined_names": defined_names,
                },
            }
    except zipfile.BadZipFile as exc:
        raise ValueError("content is not a valid XLSX ZIP package") from exc


def semantic_sha256(content: bytes) -> str:
    encoded = json.dumps(
        semantic_payload(content),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()