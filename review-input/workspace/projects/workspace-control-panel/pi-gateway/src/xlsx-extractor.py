#!/usr/bin/env python3
"""Bounded read-only XLSX extraction using only Python's standard library."""
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'pr': 'http://schemas.openxmlformats.org/package/2006/relationships'}

def col_num(value):
    result = 0
    for char in value.upper():
        result = result * 26 + ord(char) - 64
    return result

def parse_range(value):
    if not re.fullmatch(r'[A-Za-z]{1,3}[1-9][0-9]*(?::[A-Za-z]{1,3}[1-9][0-9]*)?', value or ''):
        raise ValueError('extract_range must be a bounded A1 range')
    parts = value.split(':')
    def split_cell(cell):
        match = re.fullmatch(r'([A-Za-z]{1,3})([1-9][0-9]*)', cell)
        return col_num(match.group(1)), int(match.group(2))
    start = split_cell(parts[0]); end = split_cell(parts[-1])
    return min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1])

def text_value(cell, shared):
    kind = cell.attrib.get('t')
    if kind == 'inlineStr':
        return ''.join(node.text or '' for node in cell.findall('.//m:t', NS)).strip()
    value = cell.find('m:v', NS)
    raw = '' if value is None else (value.text or '')
    if kind == 's':
        try: return shared[int(raw)]
        except (ValueError, IndexError): return raw
    return raw.strip()

def main():
    if len(sys.argv) != 4:
        print(json.dumps({'ok': False, 'code': 'XLSX_ARGUMENTS_INVALID'})); return
    filename, sheet_name, range_ref = sys.argv[1:]
    try:
        min_col, min_row, max_col, max_row = parse_range(range_ref)
        with zipfile.ZipFile(filename) as archive:
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
            rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
            rel_map = {rel.attrib['Id']: rel.attrib['Target'] for rel in rels.findall('pr:Relationship', NS)}
            sheet_nodes = workbook.findall('m:sheets/m:sheet', NS)
            sheets = [node.attrib.get('name', '') for node in sheet_nodes]
            selected = next((node for node in sheet_nodes if node.attrib.get('name') == sheet_name), None)
            if selected is None:
                print(json.dumps({'ok': False, 'code': 'XLSX_SHEET_NOT_FOUND', 'sheets': sheets[:40]})); return
            target = rel_map[selected.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            sheet_path = 'xl/' + target.lstrip('/') if not target.startswith('xl/') else target
            shared = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                shared_root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
                shared = [''.join(node.text or '' for node in item.findall('.//m:t', NS)).strip() for item in shared_root.findall('m:si', NS)]
            root = ET.fromstring(archive.read(sheet_path))
            rows = []
            for row in root.findall('.//m:sheetData/m:row', NS):
                row_num = int(row.attrib.get('r', '0'))
                if not (min_row <= row_num <= max_row): continue
                values = []
                for cell in row.findall('m:c', NS):
                    ref = cell.attrib.get('r', '')
                    match = re.fullmatch(r'([A-Za-z]{1,3})([1-9][0-9]*)', ref)
                    if not match: continue
                    col = col_num(match.group(1))
                    if min_col <= col <= max_col:
                        value = text_value(cell, shared)
                        if len(value) > 512: value = value[:512] + '…'
                        values.append({'cell': ref, 'value': value})
                if any(item['value'] for item in values): rows.append(values)
                if len(rows) >= 80: break
            print(json.dumps({'ok': True, 'workbook': Path(filename).name, 'sheets': sheets[:40], 'sheet': sheet_name, 'range': range_ref, 'row_count': len(rows), 'rows': rows}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok': False, 'code': 'XLSX_EXTRACTION_FAILED', 'message': str(exc)}))

if __name__ == '__main__': main()
