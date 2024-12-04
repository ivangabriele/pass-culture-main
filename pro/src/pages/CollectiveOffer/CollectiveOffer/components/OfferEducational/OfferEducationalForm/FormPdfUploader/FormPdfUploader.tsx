import { useState } from 'react'

import fullMoreIcon from 'icons/full-more.svg'
import { AddBankInformationsDialog } from 'pages/Reimbursements/BankInformations/AddBankInformationsDialog'
import { Button } from 'ui-kit/Button/Button'
import { ButtonVariant } from 'ui-kit/Button/types'

import { PdfUploadDialog } from './PdfUploadDialog'

export const FormPdfUploader = () => {
  const [isFileUploaded, setIsFileUploaded] = useState(false)
  const [file, setFile] = useState<File | null>(null)

  const [showPdfUploadDialog, setShowPdfUploadDialog] = useState(false)

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files
    if (files) {
      setFile(files[0])
    }
    // show success message on file upload
    setIsFileUploaded(true)
  }

  return (
    <>
      <Button
        variant={ButtonVariant.TERNARY}
        icon={fullMoreIcon}
        onClick={() => setShowPdfUploadDialog(true)}
      >
        Ajouter un document pdf
      </Button>

      <div>
        {/* <label htmlFor="pdf-input" className="pdf-input-label">
          Ajouter un document pdf
        </label>

        <input
          id="pdf-input"
          type="file"
          accept=".pdf"
          onChange={handleFileInput}
          hidden
        /> */}

        <PdfUploadDialog
          closeDialog={() => {
            setShowPdfUploadDialog(false)
          }}
          isDialogOpen={showPdfUploadDialog}
        />
      </div>
    </>
  )
}
