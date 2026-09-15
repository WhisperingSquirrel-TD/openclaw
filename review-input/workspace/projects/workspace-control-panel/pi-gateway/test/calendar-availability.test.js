'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { checkCandidateAvailability } = require('../src/calendar-availability');
const candidates = [{ label: 'Option A', start: '2026-09-02T13:00:00.000Z', end: '2026-09-02T14:00:00.000Z' }, { label: 'Option B', start: '2026-09-07T09:00:00.000Z', end: '2026-09-07T10:00:00.000Z' }];
test('checks only explicit candidate slots and returns grounded availability', async () => {
 const seen=[]; const result=await checkCandidateAvailability(candidates,{getAccessToken:async()=> 'token',graph:async(_t,endpoint)=>{seen.push(endpoint); return endpoint.includes('2026-09-02') ? {value:[{start:{dateTime:'2026-09-02T13:15:00Z'},end:{dateTime:'2026-09-02T13:45:00Z'},showAs:'busy'}]} : {value:[]};}});
 assert.equal(result.read_only,true); assert.deepEqual(result.slots.map(x=>x.status),['busy','available']); assert.equal(seen.length,2); assert.ok(seen.every(x=>x.startsWith('/me/calendarView?startDateTime=')));
});
test('fails closed when calendar access is unavailable', async () => { await assert.rejects(() => checkCandidateAvailability(candidates,{}), { code:'CALENDAR_READ_UNAVAILABLE' }); });
test('rejects broad or malformed candidate input', async () => { await assert.rejects(() => checkCandidateAvailability([], {getAccessToken:async()=>''}), {code:'SCHEDULING_CANDIDATES_INVALID'}); });
test('extracts explicit UK scheduling options in Europe/London time', () => {
 const { extractCandidateSlots } = require('../src/calendar-availability');
 const slots=extractCandidateSlots('Wednesday 2nd September at 2pm or Monday 7th September at 10am',2026);
 assert.equal(slots.length,2); assert.equal(slots[0].start,'2026-09-02T13:00:00.000Z'); assert.equal(slots[1].start,'2026-09-07T09:00:00.000Z');
});
