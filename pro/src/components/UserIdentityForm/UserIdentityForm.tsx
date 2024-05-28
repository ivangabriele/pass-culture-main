import { Form, FormikProvider, useFormik } from 'formik'
import React from 'react'
import { useDispatch } from 'react-redux'
import useSWRMutation from 'swr/mutation'

import { api } from 'apiClient/api'
import { isErrorAPIError } from 'apiClient/helpers'
import { BoxFormLayout } from 'components/BoxFormLayout/BoxFormLayout'
import { FormLayout } from 'components/FormLayout/FormLayout'
import useCurrentUser from 'hooks/useCurrentUser'
import { updateUser } from 'store/user/reducer'
import { Button } from 'ui-kit/Button/Button'
import { ButtonVariant } from 'ui-kit/Button/types'
import { TextInput } from 'ui-kit/form/TextInput/TextInput'

import { UserIdentityFormValues } from './types'
import styles from './UserIdentityForm.module.scss'
import validationSchema from './validationSchema'

export interface UserIdentityFormProps {
  closeForm: () => void
  initialValues: UserIdentityFormValues
}

const PATCH_USER_IDENTITY_QUERY_KEY = 'patchUserIdentity'

export const UserIdentityForm = ({
  closeForm,
  initialValues,
}: UserIdentityFormProps): JSX.Element => {
  const { currentUser } = useCurrentUser()
  const dispatch = useDispatch()

  const formik = useFormik({
    initialValues,
    onSubmit,
    validationSchema,
    validateOnChange: false,
  })

  const userIdentityMutation = useSWRMutation(
    PATCH_USER_IDENTITY_QUERY_KEY,
    (url, { arg }: { arg: UserIdentityFormValues }) =>
      api.patchUserIdentity(arg)
  )

  async function onSubmit(values: UserIdentityFormValues) {
    try {
      const result = await userIdentityMutation.trigger(values)
      dispatch(
        updateUser({
          ...currentUser,
          ...result,
        })
      )
      closeForm()
    } catch (error) {
      if (isErrorAPIError(error)) {
        for (const field in error.body) {
          formik.setFieldError(field, error.body[field])
        }
      }
    }
    formik.setSubmitting(false)
  }

  const onCancel = () => {
    formik.resetForm()
    closeForm()
  }

  return (
    <>
      <BoxFormLayout.RequiredMessage />
      <BoxFormLayout.Fields>
        <FormikProvider value={formik}>
          <Form onSubmit={formik.handleSubmit}>
            <FormLayout>
              <FormLayout.Row>
                <TextInput
                  label="Prénom"
                  name="firstName"
                  placeholder="Votre prénom"
                />
              </FormLayout.Row>
              <FormLayout.Row>
                <TextInput
                  label="Nom"
                  name="lastName"
                  placeholder="Votre nom"
                />
              </FormLayout.Row>
            </FormLayout>

            <div className={styles['buttons-field']}>
              <Button onClick={onCancel} variant={ButtonVariant.SECONDARY}>
                Annuler
              </Button>
              <Button type="submit" isLoading={formik.isSubmitting}>
                Enregistrer
              </Button>
            </div>
          </Form>
        </FormikProvider>
      </BoxFormLayout.Fields>
    </>
  )
}
