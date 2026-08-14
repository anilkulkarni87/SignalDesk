# NovaCart Synthetic CDP — Data Model V0

This model defines the first eight synthetic CDP tables used by SignalDesk. The design keeps customer facts deterministic while intentionally preserving realistic CDP problems such as anonymous activity, identity resolution, late events, nulls, and duplicate raw events.

## 1. `customers`

**Grain:** One row per resolved NovaCart customer.  
**Primary key:** `customer_id`  
**Purpose:** Canonical customer entity used to anchor resolved customer history.

Key fields include profile attributes, customer status, loyalty tier, timezone, and first/last seen timestamps.

---

## 2. `identities`

**Grain:** One row per identifier associated with a customer.  
**Primary key:** `identity_id`  
**Foreign key:** `customer_id -> customers.customer_id` (nullable for unresolved identities)  
**Purpose:** Models identity resolution across email, phone, cookie, device, and other identifiers.

Historical sessions may remain anonymous even when the identity is resolved later.

---

## 3. `sessions`

**Grain:** One row per browsing session.  
**Primary key:** `session_id`  
**Foreign keys:** `customer_id -> customers.customer_id`, `identity_id -> identities.identity_id`  
**Purpose:** Groups behavioral events and preserves anonymous-to-known customer behavior.

`customer_id` may be null when the session occurred before the associated identity was resolved.

---

## 4. `events`

**Grain:** One row per behavioral event.  
**Primary key:** `event_id` in the logical clean model; the raw synthetic output intentionally contains duplicate event IDs.  
**Foreign keys:** `session_id`, `customer_id`, `identity_id`, `product_id`, `order_id` where applicable.  
**Purpose:** Captures page views, product views, searches, cart activity, checkout activity, purchases, email interactions, and account activity.

`event_timestamp` represents when the event occurred. `received_at` represents when the platform received it, allowing late-arriving events to be simulated.

---

## 5. `products`

**Grain:** One row per sellable product/SKU.  
**Primary key:** `product_id`  
**Foreign keys:** None.  
**Purpose:** Product catalog used to explain customer interests and connect behavioral and transactional data.

Important fields:

- `product_id`
- `sku`
- `product_name`
- `category`
- `subcategory`
- `brand`
- `base_price`
- `cost`
- `active`
- `created_at`

SignalDesk later uses product data to answer questions such as which categories a customer is interested in and what products appeared in recent purchases.

---

## 6. `orders`

**Grain:** One row per customer order.  
**Primary key:** `order_id`  
**Foreign key:** `customer_id -> customers.customer_id`  
**Purpose:** Represents deterministic purchase history.

Important fields:

- `order_id`
- `customer_id`
- `order_timestamp`
- `status`
- `channel`
- `currency`
- `subtotal`
- `discount_amount`
- `tax_amount`
- `shipping_amount`
- `total_amount`
- `promotion_code`

The generator varies order frequency and outcomes by latent customer behavior pattern so that declining, stable, price-sensitive, dormant, and support-problem scenarios emerge from the data.

---

## 7. `order_items`

**Grain:** One row per product line within an order.  
**Primary key:** `order_item_id`  
**Foreign keys:**
- `order_id -> orders.order_id`
- `product_id -> products.product_id`

**Purpose:** Provides product-level purchase evidence.

Important fields:

- `order_item_id`
- `order_id`
- `product_id`
- `quantity`
- `unit_price`
- `line_discount`
- `line_total`

An order can contain multiple order items.

---

## 8. `support_tickets`

**Grain:** One row per customer support case.  
**Primary key:** `ticket_id`  
**Foreign keys:**
- `customer_id -> customers.customer_id`
- `order_id -> orders.order_id` when the case concerns an order

**Purpose:** Captures service problems that may explain declining customer engagement and may justify `ESCALATE_TO_SUPPORT`.

Important fields:

- `ticket_id`
- `customer_id`
- `order_id`
- `opened_at`
- `closed_at`
- `status`
- `category`
- `priority`
- `channel`
- `subject`
- `sentiment`
- `csat_score`

Support-problem customers intentionally receive more recent tickets, more negative sentiment, and a greater probability of unresolved cases.

---

# Core Relationships

```text
customers
   |
   +--- identities
   |
   +--- sessions
   |      |
   |      +--- events
   |
   +--- orders
   |      |
   |      +--- order_items ---> products
   |
   +--- support_tickets
            |
            +--- optional order reference
```

# Synthetic Data Behaviors

The generator intentionally creates:

- Stable customers
- Customers with declining recent engagement
- Customers with recent support problems
- Price-sensitive customers
- Dormant customers
- Anonymous sessions that occurred before identity resolution
- Late-arriving events
- Duplicate raw events
- Null profile attributes
- Mixed source timezones
- Refunded/canceled orders
- Open and unresolved support cases

The latent customer behavior pattern is used only by the generator to make related tables internally coherent. It is not written into the production-like customer tables.


---

# V1 Extension — Marketing, Subscription, and Consent Domains

## 9. `campaigns`

**Grain:** One row per NovaCart marketing/service campaign.  
**Primary key:** `campaign_id`  
**Purpose:** Describes the campaign that a customer may be exposed to.

Important fields:

- `campaign_id`
- `campaign_name`
- `campaign_type`
- `channel`
- `start_at`
- `end_at`
- `offer_code`
- `discount_pct`
- `audience_type`
- `active`

Campaign types include promotional, win-back, loyalty, new-arrival, and service campaigns.

---

## 10. `campaign_exposures`

**Grain:** One row per customer exposure to a campaign.  
**Primary key:** `exposure_id`  
**Foreign keys:**

- `customer_id -> customers.customer_id`
- `campaign_id -> campaigns.campaign_id`
- `converted_order_id -> orders.order_id` when conversion is attributable

**Purpose:** Captures delivery and engagement evidence such as sends, opens, clicks, and linked conversions.

Important fields:

- `exposure_id`
- `customer_id`
- `campaign_id`
- `channel`
- `sent_at`
- `delivery_status`
- `opened_at`
- `clicked_at`
- `converted_order_id`

Synthetic campaign behavior varies by hidden customer pattern:

- price-sensitive customers interact more strongly with campaigns,
- declining-engagement customers interact less than stable customers,
- dormant customers interact very little,
- support-issue customers show weaker-than-baseline engagement.

---

## 11. `subscriptions`

**Grain:** One row per customer subscription/program membership.  
**Primary key:** `subscription_id`  
**Foreign key:** `customer_id -> customers.customer_id`  
**Purpose:** Represents ongoing customer relationships such as newsletters, loyalty programs, and replenishment subscriptions.

Important fields:

- `subscription_id`
- `customer_id`
- `subscription_type`
- `status`
- `started_at`
- `ended_at`
- `renewal_at`

Statuses include:

- `ACTIVE`
- `CANCELED`
- `PAUSED`

Dormant and declining customers intentionally have lower active-subscription rates than stable customers.

---

## 12. `consent_preferences`

**Grain:** One row per customer and communication channel.  
**Primary key:** `consent_id`  
**Foreign key:** `customer_id -> customers.customer_id`  
**Purpose:** Provides deterministic communication eligibility for SignalDesk recommendations and later action workflows.

Channels:

- `EMAIL`
- `SMS`
- `PUSH`

Important fields:

- `consent_id`
- `customer_id`
- `channel`
- `status`
- `updated_at`
- `source`

Statuses:

- `OPTED_IN`
- `OPTED_OUT`

### Deterministic rule

If a customer has an effective `OPTED_OUT` status for a channel at the campaign send timestamp, the generator does not create a campaign exposure for that channel.

This rule is validated independently:

```text
effective opt-out
        ↓
campaign exposure on blocked channel
        ↓
must equal zero violations
```

This models the same system principle SignalDesk will use later: hard eligibility and consent constraints remain deterministic and cannot be overridden by an AI recommendation.

---

# Extended Relationships

```text
customers
   |
   +--- identities
   |
   +--- sessions
   |      |
   |      +--- events
   |
   +--- orders
   |      |
   |      +--- order_items ---> products
   |
   +--- support_tickets
   |
   +--- campaign_exposures ---> campaigns
   |
   +--- subscriptions
   |
   +--- consent_preferences
```

# New Semantic Validation

The extended generator now validates that:

- price-sensitive customers have materially higher campaign click rates than stable customers,
- declining customers have lower campaign open rates than stable customers,
- dormant customers have lower campaign engagement than declining customers,
- stable customers have a higher active-subscription rate than declining customers,
- declining customers have a higher active-subscription rate than dormant customers,
- effective channel opt-outs produce zero prohibited campaign exposures.
