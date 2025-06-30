import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { IconRadio } from './IconRadio'

// Dummy icon component
const DummyIcon = <svg data-testid="dummy-icon" />

describe('IconRadio', () => {
  const baseProps = {
    name: 'example',
    label: 'Option A',
    icon: DummyIcon,
  }

  it('renders label and icon', () => {
    render(<IconRadio {...baseProps} />)

    expect(screen.getByText('Option A')).toBeInTheDocument()
    expect(screen.getByTestId('dummy-icon')).toBeInTheDocument()
  })

  it('renders input with correct attributes', () => {
    render(<IconRadio {...baseProps} checked />)

    const input = screen.getByRole('radio')
    expect(input).toBeChecked()
    expect(input).toHaveAttribute('type', 'radio')
    expect(input).toHaveAttribute('name', 'example')
  })

  it('applies error class and aria-invalid when hasError is true', () => {
    render(<IconRadio {...baseProps} hasError />)

    const input = screen.getByRole('radio')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input.className).toMatch(/has-error/)
  })

  it('disables the input when disabled is true', () => {
    render(<IconRadio {...baseProps} disabled />)

    const input = screen.getByRole('radio')
    expect(input).toBeDisabled()
  })

  it('calls onChange when clicked', () => {
    const handleChange = vi.fn()
    render(<IconRadio {...baseProps} onChange={handleChange} />)

    const input = screen.getByRole('radio')
    fireEvent.click(input)
    expect(handleChange).toHaveBeenCalled()
  })

  it('calls onBlur when blurred', () => {
    const handleBlur = vi.fn()
    render(<IconRadio {...baseProps} onBlur={handleBlur} />)

    const input = screen.getByRole('radio')
    fireEvent.blur(input)
    expect(handleBlur).toHaveBeenCalled()
  })
})
