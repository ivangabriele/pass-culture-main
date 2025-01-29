import { createContext, useContext } from 'react'
import { useSelector } from 'react-redux'
import { useLocation } from 'react-router-dom'
import { useSWRConfig } from 'swr'

import { api } from 'apiClient/api'
import { OffererHeadLineOfferResponseModel } from 'apiClient/v1'
import { useAnalytics } from 'app/App/analytics/firebase'
import { GET_OFFERER_HEADLINE_OFFER_QUERY_KEY } from 'commons/config/swrQueryKeys'
import { Events } from 'commons/core/FirebaseEvents/constants'
import { useNotification } from 'commons/hooks/useNotification'
import { selectCurrentOffererId } from 'commons/store/offerer/selectors'

type UpsertHeadlineOfferParams = {
  offerId: number
  context: {
    actionType: string
    requiredImageUpload?: boolean
  }
}

type IndividualOffersContextValues = {
  headlineOffer: OffererHeadLineOfferResponseModel | null
  upsertHeadlineOffer: (params: UpsertHeadlineOfferParams) => Promise<void>
  removeHeadlineOffer: () => Promise<void>
  isHeadlineOfferAllowedForOfferer: boolean
}

const IndividualOffersContext = createContext<IndividualOffersContextValues>({
  headlineOffer: null,
  upsertHeadlineOffer: async () => {},
  removeHeadlineOffer: async () => {},
  isHeadlineOfferAllowedForOfferer: false,
})

export const useIndividualOffersContext = () => {
  return useContext(IndividualOffersContext)
}

type IndividualOffersContextProviderProps = {
  children: React.ReactNode
  isHeadlineOfferAllowedForOfferer: boolean
  headlineOffer: OffererHeadLineOfferResponseModel | null
}

export function IndividualOffersContextProvider({
  children,
  isHeadlineOfferAllowedForOfferer,
  headlineOffer,
}: IndividualOffersContextProviderProps) {
  const selectedOffererId = useSelector(selectCurrentOffererId)

  const { mutate } = useSWRConfig()
  const notify = useNotification()
  const { logEvent } = useAnalytics()
  const location = useLocation()

  const upsertHeadlineOffer = async ({
    offerId,
    context,
  }: UpsertHeadlineOfferParams) => {
    try {
      await api.upsertHeadlineOffer({ offerId })
      notify.success('Votre offre à bien été mise à la une !')
      await mutate([GET_OFFERER_HEADLINE_OFFER_QUERY_KEY, selectedOffererId])
      logEvent(Events.CLICKED_CONFIRMED_ADD_HEADLINE_OFFER, {
        from: location.pathname,
        actionType: context.actionType,
        requiredImageUpload: !!context.requiredImageUpload,
      })
    } catch {
      notify.error(
        'Une erreur s’est produite lors de l’ajout de votre offre à la une'
      )
    }
  }

  const removeHeadlineOffer = async () => {
    if (selectedOffererId) {
      try {
        await api.deleteHeadlineOffer({ offererId: selectedOffererId })
        notify.success('Votre offre n’est plus à la une')
        await mutate([GET_OFFERER_HEADLINE_OFFER_QUERY_KEY, selectedOffererId])
        logEvent(Events.CLICKED_CONFIRMED_ADD_HEADLINE_OFFER, {
          from: location.pathname,
          actionType: 'delete',
        })
      } catch {
        notify.error(
          'Une erreur s’est produite lors du retrait de votre offre à la une'
        )
      }
    }
  }

  return (
    <IndividualOffersContext.Provider
      value={{
        headlineOffer,
        upsertHeadlineOffer,
        removeHeadlineOffer,
        isHeadlineOfferAllowedForOfferer,
      }}
    >
      {children}
    </IndividualOffersContext.Provider>
  )
}
