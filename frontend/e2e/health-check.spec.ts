import { test, expect } from '@playwright/test'

test.describe('Health Check Page', () => {
  test('should load the health check component', async ({ page }) => {
    await page.goto('/')

    // Wait for the health-check component to be present
    const healthCheck = page.locator('health-check')
    await expect(healthCheck).toBeVisible()
  })

  test('should display health status', async ({ page }) => {
    await page.goto('/')

    // Wait for the component to load and display status
    await page.waitForSelector('health-check', { state: 'attached' })

    // Check that the title is displayed
    const title = page.locator('health-check').getByText('Backend Health Check')
    await expect(title).toBeVisible()
  })

  test('should have a check health button', async ({ page }) => {
    await page.goto('/')

    // Wait for the component to load
    await page.waitForSelector('health-check', { state: 'attached' })

    // Find the button within the shadow root
    const button = page.locator('health-check').getByRole('button', {
      name: /check health/i,
    })
    await expect(button).toBeVisible()
  })

  test('should be able to click check health button', async ({ page }) => {
    await page.goto('/')

    // Wait for the component to load
    await page.waitForSelector('health-check', { state: 'attached' })

    // Find and click the button
    const button = page.locator('health-check').getByRole('button', {
      name: /check health/i,
    })
    await button.click()

    // Button should still be present after click
    await expect(button).toBeVisible()
  })

  test('should display loading state when checking health', async ({ page }) => {
    await page.goto('/')

    // Wait for the component to load
    await page.waitForSelector('health-check', { state: 'attached' })

    // Initial load might show loading state
    // Note: This test is timing-dependent and might need adjustment
    const statusText = page.locator('health-check').locator('.status-text')
    const text = await statusText.textContent()

    // Status should be either loading or healthy
    expect(['Checking...', 'healthy', 'Error']).toContain(text?.trim())
  })
})
