'use strict';
// Bounded availability evidence for explicit scheduling options. This module never
// searches calendars: callers must supply parsed candidate slots and it queries
// only each candidate's exact interval, read-only.
const GRAPH_BASE = 'https://graph.microsoft.com/v1.0';
const MAX_CANDIDATES = 4;
const SLOT_MS = 60 * 60 * 1000;

function iso(value) { return new Date(value).toISOString(); }
function validSlot(slot) { return slot && typeof slot.start === 'string' && typeof slot.end === 'string' && !Number.isNaN(Date.parse(slot.start)) && !Number.isNaN(Date.parse(slot.end)) && Date.parse(slot.end) > Date.parse(slot.start); }
function normaliseCandidates(candidates) {
  if (!Array.isArray(candidates) || !candidates.length || candidates.length > MAX_CANDIDATES || candidates.some(slot => !validSlot(slot))) {
    const err = new Error('Scheduling availability requires 1–4 explicit valid candidate slots'); err.code = 'SCHEDULING_CANDIDATES_INVALID'; throw err;
  }
  return candidates.map(slot => ({ start: iso(slot.start), end: iso(slot.end), label: String(slot.label || '').slice(0, 160) || null }));
}
function extractCandidateSlots(text, year = new Date().getFullYear()) {
  const months = { january:0, february:1, march:2, april:3, may:4, june:5, july:6, august:7, september:8, october:9, november:10, december:11 };
  const re = /(?:\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(\d{4}))?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b/ig;
  const slots = []; let match;
  while ((match = re.exec(String(text || ''))) && slots.length < MAX_CANDIDATES) {
    const [, day, monthName, explicitYear, hourText, minuteText, meridiem] = match; let hour = Number(hourText) % 12; if (meridiem.toLowerCase() === 'pm') hour += 12;
    const y = Number(explicitYear || year); const m = months[monthName.toLowerCase()]; const d = Number(day);
    // Proposed meeting times are interpreted in Tom's Europe/London timezone. This implementation deliberately supports the explicit UK format only; unparseable wording remains coverage-incomplete.
    const local = Date.UTC(y, m, d, hour, Number(minuteText || 0)); const dst = m > 2 && m < 9; const start = new Date(local - (dst ? 3600000 : 0));
    slots.push({ label: match[0], start: start.toISOString(), end: new Date(start.getTime() + SLOT_MS).toISOString() });
  }
  return slots;
}
function overlaps(event, slot) { return Date.parse(event.start?.dateTime || event.start) < Date.parse(slot.end) && Date.parse(event.end?.dateTime || event.end) > Date.parse(slot.start); }
async function checkCandidateAvailability(candidates, deps = {}) {
  const slots = normaliseCandidates(candidates);
  const getAccessToken = deps.getAccessToken;
  const graph = deps.graph || (async (token, endpoint) => {
    const response = await fetch(`${GRAPH_BASE}${endpoint}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { const err = new Error(`Microsoft calendar read failed: ${response.status}`); err.code = response.status === 401 || response.status === 403 ? 'CALENDAR_READ_UNAUTHORISED' : 'CALENDAR_READ_UNAVAILABLE'; throw err; }
    return response.json();
  });
  if (typeof getAccessToken !== 'function') { const err = new Error('Calendar read capability is not configured'); err.code = 'CALENDAR_READ_UNAVAILABLE'; throw err; }
  const token = await getAccessToken();
  const results = [];
  for (const slot of slots) {
    const query = `/me/calendarView?startDateTime=${encodeURIComponent(slot.start)}&endDateTime=${encodeURIComponent(slot.end)}&$select=start,end,showAs,isCancelled`;
    const response = await graph(token, query);
    const busy = (response.value || []).some(event => !event.isCancelled && event.showAs !== 'free' && overlaps(event, slot));
    results.push({ ...slot, status: busy ? 'busy' : 'available' });
  }
  return { schema: 'candidate-slot-availability-v1', retrieval_scope: 'explicit_candidate_slots_only', read_only: true, slots: results };
}
module.exports = { MAX_CANDIDATES, SLOT_MS, normaliseCandidates, extractCandidateSlots, checkCandidateAvailability };
