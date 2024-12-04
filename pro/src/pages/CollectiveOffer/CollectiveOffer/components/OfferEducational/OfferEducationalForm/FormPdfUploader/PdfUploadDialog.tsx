import { useRef, useState } from 'react'

import { Dialog } from 'components/Dialog/Dialog/Dialog'
import strokeShareIcon from 'icons/stroke-share.svg'
import { Button } from 'ui-kit/Button/Button'
import { ButtonVariant } from 'ui-kit/Button/types'

interface PdfUploadModalProps {
  closeDialog: () => void
  isDialogOpen: boolean
}

export const PdfUploadDialog = ({
  closeDialog,
  isDialogOpen,
}: PdfUploadModalProps): JSX.Element => {
  const [isFileUploaded, setIsFileUploaded] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  // const [progress, setProgress] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files
    if (files) {
      setFile(files[0])
    }
    setIsFileUploaded(true)
  }

  const handleUploadFile = () => {
    if (inputRef.current) {
      inputRef.current.click()
    }
  }

  const onCloseDialog = () => {
    setFile(null)
    closeDialog()
  }

  return (
    <Dialog
      title="Ajouter un document"
      icon={strokeShareIcon}
      onCancel={onCloseDialog}
      open={isDialogOpen}
    >
      <div>
        <p>Attention ce pdf ne doit pas remplacer la description... :</p>
        <ul>
          <li>Pas de prix</li>
          <li>Pas de cv</li>
        </ul>
      </div>

      {/* <label htmlFor="pdf-input" className="">
        <strong>Importer un document depuis l’ordinateur</strong>
      </label> */}

      {!file && (
        <>
          <Button variant={ButtonVariant.PRIMARY} onClick={handleUploadFile}>
            Importer un document depuis l’ordinateur
          </Button>

          <input
            ref={inputRef}
            id="pdf-input"
            type="file"
            accept=".pdf"
            onChange={handleFileInput}
            hidden
          />
        </>
      )}

      {file && (
        <>
          <p>{file.name}</p>
          {/* <progress /> */}
          <Button
            variant={ButtonVariant.PRIMARY}
            // onClick={handleConfirmUploadFile}
          >
            Confirmer
          </Button>
        </>
      )}
    </Dialog>
  )
}
