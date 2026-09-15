/**
 * Playwright script — Anthropic job application
 * Role: Technical Deployment Lead, Applied AI
 * Job ID: 5128818008
 *
 * Prerequisites:
 *   npm install playwright
 *   npx playwright install chromium
 *
 * Before running:
 *   1. Export your CV as a PDF and set CV_PATH below
 *   2. Export your cover letter as a PDF (or plain text) and set COVER_LETTER_PATH
 *   3. Run: node apply-anthropic.js
 *   4. Script will PAUSE before submitting — you review and press Enter to confirm
 *
 * Usage:
 *   node apply-anthropic.js
 */

const { chromium } = require('playwright');
const readline = require('readline');
const path = require('path');

// ── Config ──────────────────────────────────────────────────────────────────
const JOB_URL = 'https://job-boards.greenhouse.io/anthropic/jobs/5128818008';

const APPLICANT = {
  firstName:  'Tom',
  lastName:   'Dean',
  email:      'tomdean1988@gmail.com',
  phone:      '+447894241276',
  location:   'Abingdon, Oxfordshire, United Kingdom',
  linkedin:   'https://www.linkedin.com/in/tomadean',
  website:    'https://stackstoneconsulting.co.uk',
};

// ⚠️  SET THESE PATHS before running
const CV_PATH           = path.resolve('./cv-anthropic-2026-03-02.pdf');
const COVER_LETTER_PATH = path.resolve('./cover-letter-anthropic-2026-03-02.pdf');
// ────────────────────────────────────────────────────────────────────────────

async function pause(message) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve => {
    rl.question(`\n${message}\nPress Enter to continue (Ctrl+C to abort)...`, () => {
      rl.close();
      resolve();
    });
  });
}

async function fillField(page, label, value) {
  try {
    const field = page.getByLabel(label, { exact: false });
    await field.waitFor({ timeout: 3000 });
    await field.fill(value);
    console.log(`  ✓ ${label}`);
  } catch {
    console.warn(`  ⚠ Could not find field: "${label}" — fill manually`);
  }
}

(async () => {
  console.log('🚀 Starting Anthropic application script...\n');

  const browser = await chromium.launch({ headless: false, slowMo: 100 });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('📄 Loading application page...');
  await page.goto(JOB_URL, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  console.log('\n📝 Filling personal details...');
  await fillField(page, 'First Name', APPLICANT.firstName);
  await fillField(page, 'Last Name',  APPLICANT.lastName);
  await fillField(page, 'Email',      APPLICANT.email);
  await fillField(page, 'Phone',      APPLICANT.phone);
  await fillField(page, 'Location',   APPLICANT.location);
  await fillField(page, 'LinkedIn',   APPLICANT.linkedin);
  await fillField(page, 'Website',    APPLICANT.website);

  // CV upload
  console.log('\n📎 Uploading CV...');
  try {
    const cvInput = page.locator('input[type="file"]').first();
    await cvInput.setInputFiles(CV_PATH);
    console.log('  ✓ CV uploaded');
  } catch {
    console.warn('  ⚠ CV upload failed — attach manually in the browser');
  }

  // Cover letter upload (Greenhouse sometimes uses a second file input)
  console.log('\n📎 Uploading cover letter...');
  try {
    const inputs = await page.locator('input[type="file"]').all();
    if (inputs.length > 1) {
      await inputs[1].setInputFiles(COVER_LETTER_PATH);
      console.log('  ✓ Cover letter uploaded');
    } else {
      console.warn('  ⚠ No second file input found — paste cover letter text manually if prompted');
    }
  } catch {
    console.warn('  ⚠ Cover letter upload failed — handle manually');
  }

  // Demographic / voluntary fields (Greenhouse standard — skip/prefer not to say)
  // These are optional — leave for you to complete in the browser

  console.log('\n✅ Fields filled. Browser is open for your review.');
  console.log('   - Check all fields look correct');
  console.log('   - Complete any additional questions or dropdowns');
  console.log('   - DO NOT click Submit yet\n');

  await pause('👀 Review the form now. When you are happy and ready to submit...');

  console.log('\n🔴 Final check — about to submit the application.');
  await pause('⚠️  LAST CHANCE TO ABORT. Press Enter to submit, Ctrl+C to cancel.');

  try {
    const submitBtn = page.getByRole('button', { name: /submit/i });
    await submitBtn.click();
    await page.waitForTimeout(3000);
    console.log('\n🎉 Application submitted! Check tomdean1988@gmail.com for confirmation.');
  } catch {
    console.warn('\n⚠ Submit button not found — click it manually in the browser.');
  }

  await pause('Press Enter to close the browser when done.');
  await browser.close();
})();
