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
