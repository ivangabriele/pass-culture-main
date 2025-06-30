import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RadioGroup, RadioGroupProps } from './RadioGroup'

const defaultProps: RadioGroupProps = {
  name: 'test-group',
  legend: 'Choose an option',
  group: [
    { label: 'Option A', value: 'a' },
    { label: 'Option B', value: 'b' },
    { label: 'Option C', value: 'c' },
  ],
  onChange: vi.fn(),
}

describe('RadioGroup', () => {
  it('renders with legend and all options', () => {
    render(<RadioGroup {...defaultProps} />)

    // Check for legend
    expect(screen.getByText('Choose an option')).toBeInTheDocument()

    // Check for each radio label
    defaultProps.group.forEach((item) => {
      expect(screen.getByLabelText(item.label)).toBeInTheDocument()
    })
  })

  it('uses describedBy when legend is not present', () => {
    const props: RadioGroupProps = {
      ...defaultProps,
      legend: '',
      describedBy: 'custom-desc',
    }

    render(<RadioGroup {...props} />)

    const fieldset = screen.getByTestId(`wrapper-${props.name}`)
    expect(fieldset).toHaveAttribute('aria-describedby', 'custom-desc')
  })

  it('handles checkedOption properly', () => {
    const props = {
      ...defaultProps,
      checkedOption: 'b',
    }

    render(<RadioGroup {...props} />)

    const checkedRadio = screen.getByDisplayValue('b')
    expect(checkedRadio).toBeChecked()
  })

  it('calls onChange when an option is selected', () => {
    const handleChange = vi.fn()
    const props = {
      ...defaultProps,
      onChange: handleChange,
    }

    render(<RadioGroup {...props} />)

    const radio = screen.getByLabelText('Option B')
    fireEvent.click(radio)

    expect(handleChange).toHaveBeenCalled()
  })

  it('applies the correct displayMode class', () => {
    const props = {
      ...defaultProps,
      displayMode: 'inline-grow' as const,
    }

    render(<RadioGroup {...props} />)

    expect(
      screen
        .getByTestId(`wrapper-${props.name}`)
        .querySelector('.radio-group-display-inline-grow')
    ).toBeInTheDocument()
  })

  it('renders detailed variant when specified', () => {
    const props = {
      ...defaultProps,
      variant: 'detailed' as const,
    }

    render(<RadioGroup {...props} />)

    const radios = screen.getAllByRole('radio')
    expect(radios.length).toBe(defaultProps.group.length)
    radios.forEach((radio) => {
      expect(radio).toHaveAttribute('type', 'radio')
    })
  })
})
