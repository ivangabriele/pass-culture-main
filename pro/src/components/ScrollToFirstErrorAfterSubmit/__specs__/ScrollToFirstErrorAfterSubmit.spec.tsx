import { render, screen, waitFor } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'

import { Button } from 'ui-kit/Button/Button'
import { TextInput } from 'ui-kit/form/TextInput/TextInput'

import { ScrollToFirstHookFormErrorAfterSubmit } from '../ScrollToFirstErrorAfterSubmit'

const scrollIntoViewMock = vi.fn()

vi.mock('commons/utils/windowMatchMedia', () => ({
  doesUserPreferReducedMotion: vi.fn(() => true),
}))

const TestComponent = () => {
  return (
    <form>
      <TextInput name="test" label="test" />
      <Button type="submit">Enregistrer</Button>

      <ScrollToFirstHookFormErrorAfterSubmit />
    </form>
  )
}

const renderScrollToFirstErrorAfterSubmit = () => {
  return render(<TestComponent />)
}

describe('ScrollToFirstErrorAfterSubmit', () => {
  it('should scroll into view and give focus', async () => {
    Element.prototype.scrollIntoView = scrollIntoViewMock

    renderScrollToFirstErrorAfterSubmit()

    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => {
      expect(screen.getByText('Veuillez remplir le champ')).toBeInTheDocument()
    })
    expect(scrollIntoViewMock).toHaveBeenCalled()
    expect(screen.getByLabelText('test *')).toHaveFocus()
  })
})
