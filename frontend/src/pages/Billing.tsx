import React from 'react';
import { useMutation, useQuery } from 'react-query';
import { Check, CreditCard, ExternalLink } from 'lucide-react';
import { toast } from 'react-hot-toast';

import { billingAPI } from '../services/api';
import { CustomerSubscription, SubscriptionPlan } from '../types/api';

const Billing: React.FC = () => {
  const plansQuery = useQuery('billing-plans', billingAPI.getPlans);
  const subscriptionQuery = useQuery('billing-subscription', billingAPI.getSubscription);

  const checkout = useMutation((planId: number) => billingAPI.createCheckout(planId), {
    onSuccess: ({ data }) => {
      window.location.assign(data.checkout_url);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Unable to start checkout');
    },
  });

  const portal = useMutation(billingAPI.createPortal, {
    onSuccess: ({ data }) => {
      window.location.assign(data.portal_url);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Unable to open billing portal');
    },
  });

  const plans: SubscriptionPlan[] = plansQuery.data?.data?.plans || [];
  const subscription: CustomerSubscription | null =
    subscriptionQuery.data?.data?.subscription || null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Plans & Billing</h1>
          <p className="mt-1 text-sm text-gray-500">
            Choose a plan and manage your subscription securely through Stripe.
          </p>
        </div>
        {subscription && (
          <button
            className="btn-secondary flex items-center justify-center"
            onClick={() => portal.mutate()}
            disabled={portal.isLoading}
          >
            <CreditCard className="mr-2 h-4 w-4" />
            Manage billing
            <ExternalLink className="ml-2 h-4 w-4" />
          </button>
        )}
      </div>

      {subscription && (
        <div className="card border border-primary-100 bg-primary-50">
          <p className="text-sm text-primary-700">Current subscription</p>
          <div className="mt-1 flex flex-wrap items-baseline gap-3">
            <span className="text-xl font-bold capitalize">{subscription.plan_tier}</span>
            <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase text-primary-700">
              {subscription.status}
            </span>
            {subscription.current_period_end && (
              <span className="text-sm text-gray-600">
                Renews through {new Date(subscription.current_period_end).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
      )}

      {plansQuery.isLoading ? (
        <div className="card text-center text-gray-500">Loading plans…</div>
      ) : plansQuery.isError ? (
        <div className="card text-center text-danger">Unable to load plans.</div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {plans.map((plan) => {
            const isCurrent = subscription?.plan_tier === plan.tier;
            return (
              <div key={plan.id} className={`card flex flex-col ${isCurrent ? 'ring-2 ring-primary-500' : ''}`}>
                <div>
                  <p className="text-sm font-semibold uppercase tracking-wide text-primary-600">
                    {plan.display_name}
                  </p>
                  <div className="mt-3 flex items-baseline">
                    <span className="text-3xl font-bold">
                      {new Intl.NumberFormat('en-US', {
                        style: 'currency',
                        currency: plan.currency,
                        maximumFractionDigits: 0,
                      }).format(plan.price)}
                    </span>
                    <span className="ml-1 text-sm text-gray-500">/{plan.billing_interval}</span>
                  </div>
                  <p className="mt-3 text-sm text-gray-600">{plan.description}</p>
                </div>

                <ul className="my-6 flex-1 space-y-3">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex text-sm text-gray-700">
                      <Check className="mr-2 h-4 w-4 shrink-0 text-success" />
                      {feature.replace(/_/g, ' ')}
                    </li>
                  ))}
                </ul>

                <button
                  className={isCurrent ? 'btn-secondary w-full' : 'btn-primary w-full'}
                  disabled={isCurrent || checkout.isLoading || plan.price === 0}
                  onClick={() => checkout.mutate(plan.id)}
                >
                  {isCurrent ? 'Current plan' : plan.price === 0 ? 'Free plan' : 'Choose plan'}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Billing;
