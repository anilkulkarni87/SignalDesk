# Customer 360 Lineage

```mermaid
flowchart TD
    C[raw customers] --> SC[stg_customers]
    I[raw identities] --> SI[stg_identities]
    S[raw sessions] --> SS[stg_sessions]
    E[raw events] --> SE[stg_events_deduped]
    O[raw orders] --> SO[stg_orders]
    OI[raw order_items] --> SOI[stg_order_items]
    P[raw products] --> SP[stg_products]
    T[raw support_tickets] --> ST[stg_support_tickets]
    CE[raw campaign_exposures] --> SCE[stg_campaign_exposures]
    SUB[raw subscriptions] --> SSUB[stg_subscriptions]
    CP[raw consent_preferences] --> SCP[stg_consent_preferences]

    SI --> SS
    SI --> SE

    SC --> IDF[int_customer_identity_features]
    SI --> IDF

    SO --> PF[int_customer_purchase_features]
    SOI --> PF
    SP --> PF

    SS --> EF[int_customer_engagement_features]
    SE --> EF

    ST --> SF[int_customer_support_features]
    SCE --> CF[int_customer_campaign_features]
    SSUB --> SUF[int_customer_subscription_features]
    SCP --> COF[int_customer_consent_features]

    SC --> C360[customer_360]
    IDF --> C360
    PF --> C360
    EF --> C360
    SF --> C360
    CF --> C360
    SUF --> C360
    COF --> C360
```

## Important boundaries

- Raw data is never mutated.
- Event duplicates are removed only in staging.
- Anonymous raw activity is preserved; a resolved customer key is added separately.
- Intermediate marts remain domain-specific so each feature family can be reconciled independently.
- `customer_360` is a join of deterministic marts, not a place for hidden business logic.
