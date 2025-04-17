import * as Dialog from '@radix-ui/react-dialog'
import { useRef, useState } from 'react'
import AvatarEditor, { CroppedRect, Position } from 'react-avatar-editor'
import Cropper from 'react-easy-crop'

import { useAnalytics } from 'app/App/analytics/firebase'
import { Events } from 'commons/core/FirebaseEvents/constants'
import { useGetImageBitmap } from 'commons/hooks/useGetBitmap'
import { useNotification } from 'commons/hooks/useNotification'
import homeShell from 'components/ImageUploader/assets/offer-home-shell.png'
import offerShell from 'components/ImageUploader/assets/offer-shell.png'
import { ImageEditorConfig } from 'components/ImageUploader/components/ButtonImageEdit/ModalImageEdit/components/ModalImageCrop/ImageEditor/ImageEditor'
import { coordonateToPosition } from 'components/ImageUploader/components/ButtonImageEdit/ModalImageEdit/components/ModalImageCrop/ImageEditor/utils'
import { modeValidationConstraints } from 'components/ImageUploader/components/ButtonImageEdit/ModalImageEdit/components/ModalImageUploadBrowser/ImageUploadBrowserForm/constants'
import { AppPreviewOffer } from 'components/ImageUploader/components/ImagePreview/components/AppPreviewOffer/AppPreviewOffer'
import { ImagePreview } from 'components/ImageUploader/components/ImagePreview/ImagePreview'
import { ImagePreviewsWrapper } from 'components/ImageUploader/components/ImagePreview/ImagePreviewsWrapper'
import { UploaderModeEnum } from 'components/ImageUploader/types'
import fullDownloadIcon from 'icons/full-download.svg'
import fullTrashIcon from 'icons/full-trash.svg'
import { Button } from 'ui-kit/Button/Button'
import { ButtonVariant } from 'ui-kit/Button/types'
import { DialogBuilder } from 'ui-kit/DialogBuilder/DialogBuilder'
import { Slider } from 'ui-kit/form/Slider/Slider'
import { TextInput } from 'ui-kit/formV2/TextInput/TextInput'

import { getCropMaxDimension } from '../../utils/getCropMaxDimension'

import homeStyle from './HomeScreenPreview.module.scss'
import style from './ModalImageCrop.module.scss'
import offerStyle from './OfferScreenPreview.module.scss'

export type ModalImageCropProps = {
  image: File
  initialCredit?: string | null
  children?: never
  onReplaceImage: () => void
  onImageDelete: () => void
  initialPosition?: Position
  initialScale?: number
  saveInitialPosition: (position: Position) => void
  onEditedImageSave: (
    credit: string | null,
    dataUrl: string,
    croppedRect: CroppedRect
  ) => void
  mode: UploaderModeEnum
  imageUrl?: string
}

const CROP_AREA_ASPECT = 3 / 2

export const ModalImageCrop = ({
  image,
  initialCredit,
  onReplaceImage,
  onImageDelete,
  onEditedImageSave,
  saveInitialPosition,
  initialPosition,
  initialScale,
  mode,
  imageUrl,
}: ModalImageCropProps): JSX.Element => {
  const { logEvent } = useAnalytics()
  const { width, height } = useGetImageBitmap(image)
  const editorRef = useRef(null)
  const notification = useNotification()
  const [credit, setCredit] = useState(initialCredit || '')
  const [dataUrl, setDataUrl] = useState<string>(
    URL.createObjectURL(image) || ''
  )
  const [crop, setCrop] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [croppedArea, setCroppedArea] = useState(null)
  const [initialCroppedArea, setInitialCroppedArea] = useState(undefined)

  const minWidth = modeValidationConstraints[mode].minWidth

  const { width: maxWidth } = getCropMaxDimension({
    originalDimensions: { width, height },
    orientation: mode === UploaderModeEnum.VENUE ? 'landscape' : 'portrait',
  })

  const AppPreview = {
    [UploaderModeEnum.VENUE]: () => <></>,
    [UploaderModeEnum.OFFER]: AppPreviewOffer,
    [UploaderModeEnum.OFFER_COLLECTIVE]: () => <></>,
  }[mode]

  const maxScale: number = Math.min(4, (maxWidth - 10) / minWidth)

  const canvasHeight: number = {
    [UploaderModeEnum.OFFER]: 297,
    [UploaderModeEnum.OFFER_COLLECTIVE]: 297,
    [UploaderModeEnum.VENUE]: 138,
  }[mode]

  const imageEditorConfig: ImageEditorConfig = {
    [UploaderModeEnum.OFFER]: {
      cropAreaAspect: 2 / 3,
    },
    [UploaderModeEnum.OFFER_COLLECTIVE]: {
      cropAreaAspect: 2 / 3,
    },
    [UploaderModeEnum.VENUE]: {
      cropAreaAspect: 3 / 2,
    },
  }[mode]

  const handleImageChange = (
    callback?:
      | ((
          credit: string | null,
          url: string,
          cropping: AvatarEditor.CroppedRect
        ) => void)
      | undefined
  ) => {
    logEvent(Events.CLICKED_ADD_IMAGE, {
      imageCreationStage: 'reframe image',
    })

    try {
      if (editorRef) {
        const canvas = editorRef.current.getImage()
        setDataUrl(canvas.toDataURL())

        const croppingRect = editorRef.current.getCroppingRect()

        saveInitialPosition({
          x: coordonateToPosition(croppingRect.x, croppingRect.width),
          y: coordonateToPosition(croppingRect.y, croppingRect.height),
        })

        if (callback) {
          callback(credit, canvas.toDataURL(), croppingRect)
        }
      }
    } catch {
      notification.error(
        'Une erreur est survenue. Merci de réessayer plus tard'
      )
    }
  }

  function handleSave() {
    return handleImageChange(onEditedImageSave)
  }

  const onCropComplete = (croppedArea, croppedAreaPixels) => {
    console.log(croppedArea, croppedAreaPixels)
  }

  return (
    <form className={style['modal-image-crop']}>
      <div className={style['modal-image-crop-content']}>
        <Dialog.Title asChild>
          <h1 className={style['modal-image-crop-header']}>
            Modifier une image
          </h1>
        </Dialog.Title>

        <p className={style['modal-image-crop-right']}>
          En utilisant ce contenu, je certifie que je suis propriétaire ou que
          je dispose des autorisations nécessaires pour l’utilisation de
          celui-ci.
        </p>

        <div className={style['modal-image-crop-wrapper']}>
          <div className={style['modal-image-crop-editor']}>
            <div className={style['cropper']}>
              <Cropper
                image={dataUrl}
                aspect={imageEditorConfig.cropAreaAspect}
                crop={crop}
                zoom={zoom}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropAreaChange={setCroppedArea}
                onCropComplete={onCropComplete}
                ref={editorRef}
              />
            </div>
            <Slider
              name="scale"
              step={0.01}
              max={maxScale > 1 ? maxScale.toFixed(2) : 1}
              min={1}
              displayMinMaxValues={false}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
            />
            <div className={style['modal-image-crop-actions']}>
              <Button
                icon={fullDownloadIcon}
                onClick={onReplaceImage}
                variant={ButtonVariant.TERNARY}
              >
                Remplacer l’image
              </Button>

              <Dialog.Close asChild>
                <Button
                  icon={fullTrashIcon}
                  onClick={onImageDelete}
                  variant={ButtonVariant.TERNARY}
                >
                  Supprimer l’image
                </Button>
              </Dialog.Close>
            </div>
          </div>
          {croppedArea && (
            <Output croppedArea={croppedArea} zoom={zoom} imageUrl={dataUrl} />
          )}
        </div>

        <TextInput
          count={credit.length}
          className={style['modal-image-crop-credit']}
          label="Crédit de l’image"
          maxLength={255}
          value={credit}
          onChange={(e) => setCredit(e.target.value)}
          name="credit"
          type="text"
        />
      </div>

      <DialogBuilder.Footer>
        <div className={style['modal-image-crop-footer']}>
          <Dialog.Close asChild>
            <Button variant={ButtonVariant.SECONDARY}>Annuler</Button>
          </Dialog.Close>
          <Button
            type="submit"
            onClick={(e) => {
              e.preventDefault()
              handleSave()
            }}
          >
            Enregistrer
          </Button>
        </div>
      </DialogBuilder.Footer>
    </form>
  )
}

// Define the type for the cropped area
export type CroppedArea = {
  x: number
  y: number
  width: number
  height: number
}

// Define the type for the props of Output component
export type OutputProps = {
  croppedArea: CroppedArea
  imageUrl: string
  zoom: number // Add zoom prop here
}

export const Output = ({ croppedArea, zoom, imageUrl }: OutputProps) => {
  const clipLeft = `${croppedArea.x}%`
  const clipTop = `${croppedArea.y}%`
  const clipRight = `${100 - (croppedArea.x + croppedArea.width)}%`
  const clipBottom = `${100 - (croppedArea.y + croppedArea.height)}%`

  const imageStyle = {
    objectFit: 'cover',
    width: '100%', // Keep the width of the image filling the container
    height: '100%', // Keep the height of the image filling the container
    clipPath: `inset(${clipTop} ${clipRight} ${clipBottom} ${clipLeft})`,
    transition: 'clip-path 0.3s ease-in-out',
    transform: `scale(${zoom})`, // Apply zoom transformation to the image
    transformOrigin: 'top left', // Anchor the zoom to the top-left corner
    objectPosition: `top left`, // Keep the image aligned to the top-left corner
  }

  return (
    <ImagePreviewsWrapper>
      <ImagePreview title="Page d’accueil">
        <img
          alt=""
          className={homeStyle['image-preview-shell']}
          src={homeShell}
          role="presentation"
        />
        <div style={{ width: '36px', height: '54px' }}>
          <img
            data-testid="app-preview-offer-img-home"
            alt=""
            width={'70px'}
            className={homeStyle['image-preview-home-preview']}
            src={imageUrl}
            role="presentation"
            style={imageStyle}
          />
        </div>
      </ImagePreview>
      <ImagePreview title="Détails de l’offre">
        <img
          alt=""
          className={offerStyle['image-preview-blur-offer-preview']}
          src={imageUrl}
          role="presentation"
        />
        <img
          alt=""
          className={offerStyle['image-preview-shell']}
          src={offerShell}
          role="presentation"
        />
        <img
          data-testid="app-preview-offer-img"
          alt=""
          className={offerStyle['image-preview-offer-preview']}
          src={imageUrl}
          role="presentation"
          style={imageStyle}
        />
      </ImagePreview>
    </ImagePreviewsWrapper>
  )
}
