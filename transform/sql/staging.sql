-- Commit 03: staging layer
-- Raw views are registered by build_customer_360.py.

CREATE OR REPLACE TABLE stg_customers AS
SELECT
    CAST(customer_id AS VARCHAR) AS customer_id,
    TRY_CAST(created_at AS TIMESTAMPTZ) AS created_at,
    CAST(country AS VARCHAR) AS country,
    CAST(loyalty_tier AS VARCHAR) AS loyalty_tier,
    CAST(customer_status AS VARCHAR) AS customer_status,
    CAST(timezone AS VARCHAR) AS timezone
FROM raw_customers;

CREATE OR REPLACE TABLE stg_identities AS
SELECT
    CAST(identity_id AS VARCHAR) AS identity_id,
    NULLIF(TRIM(CAST(customer_id AS VARCHAR)), '') AS customer_id,
    CAST(identity_type AS VARCHAR) AS identity_type,
    TRY_CAST(first_seen_at AS TIMESTAMPTZ) AS first_seen_at,
    TRY_CAST(last_seen_at AS TIMESTAMPTZ) AS last_seen_at,
    TRY_CAST(resolved_at AS TIMESTAMPTZ) AS resolved_at,
    CAST(resolution_method AS VARCHAR) AS resolution_method
FROM raw_identities;

CREATE OR REPLACE TABLE stg_sessions AS
SELECT
    CAST(s.session_id AS VARCHAR) AS session_id,
    NULLIF(TRIM(CAST(s.customer_id AS VARCHAR)), '') AS observed_customer_id,
    COALESCE(
        NULLIF(TRIM(CAST(s.customer_id AS VARCHAR)), ''),
        i.customer_id
    ) AS resolved_customer_id,
    CAST(s.identity_id AS VARCHAR) AS identity_id,
    TRY_CAST(s.session_started_at AS TIMESTAMPTZ) AS session_started_at,
    TRY_CAST(s.session_ended_at AS TIMESTAMPTZ) AS session_ended_at,
    CAST(s.channel AS VARCHAR) AS channel
FROM raw_sessions s
LEFT JOIN stg_identities i
    ON CAST(s.identity_id AS VARCHAR) = i.identity_id;

CREATE OR REPLACE TABLE stg_events AS
WITH normalized AS (
    SELECT
        CAST(e.event_id AS VARCHAR) AS event_id,
        CAST(e.event_type AS VARCHAR) AS event_type,
        TRY_CAST(e.event_timestamp AS TIMESTAMPTZ) AS event_timestamp,
        TRY_CAST(e.received_at AS TIMESTAMPTZ) AS received_at,
        NULLIF(TRIM(CAST(e.customer_id AS VARCHAR)), '') AS observed_customer_id,
        CAST(e.identity_id AS VARCHAR) AS identity_id,
        CAST(e.session_id AS VARCHAR) AS session_id,
        NULLIF(TRIM(CAST(e.product_id AS VARCHAR)), '') AS product_id,
        NULLIF(TRIM(CAST(e.order_id AS VARCHAR)), '') AS order_id
    FROM raw_events e
),
deduped AS (
    SELECT *
    FROM normalized
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY event_id
        ORDER BY received_at ASC
    ) = 1
)
SELECT
    d.*,
    COALESCE(d.observed_customer_id, i.customer_id) AS resolved_customer_id
FROM deduped d
LEFT JOIN stg_identities i
    ON d.identity_id = i.identity_id;

CREATE OR REPLACE TABLE stg_orders AS
SELECT
    CAST(order_id AS VARCHAR) AS order_id,
    CAST(customer_id AS VARCHAR) AS customer_id,
    TRY_CAST(order_timestamp AS TIMESTAMPTZ) AS order_timestamp,
    CAST(status AS VARCHAR) AS status,
    CAST(channel AS VARCHAR) AS channel,
    TRY_CAST(total_amount AS DOUBLE) AS total_amount,
    TRY_CAST(discount_amount AS DOUBLE) AS discount_amount
FROM raw_orders;

CREATE OR REPLACE TABLE stg_order_items AS
SELECT
    CAST(order_item_id AS VARCHAR) AS order_item_id,
    CAST(order_id AS VARCHAR) AS order_id,
    CAST(product_id AS VARCHAR) AS product_id,
    TRY_CAST(quantity AS BIGINT) AS quantity,
    TRY_CAST(unit_price AS DOUBLE) AS unit_price,
    TRY_CAST(line_discount AS DOUBLE) AS line_discount,
    TRY_CAST(line_total AS DOUBLE) AS line_total
FROM raw_order_items;

CREATE OR REPLACE TABLE stg_products AS
SELECT
    CAST(product_id AS VARCHAR) AS product_id,
    CAST(category AS VARCHAR) AS category,
    CAST(subcategory AS VARCHAR) AS subcategory,
    CAST(brand AS VARCHAR) AS brand
FROM raw_products;

CREATE OR REPLACE TABLE stg_support_tickets AS
SELECT
    CAST(ticket_id AS VARCHAR) AS ticket_id,
    CAST(customer_id AS VARCHAR) AS customer_id,
    NULLIF(TRIM(CAST(order_id AS VARCHAR)), '') AS order_id,
    TRY_CAST(opened_at AS TIMESTAMPTZ) AS opened_at,
    TRY_CAST(closed_at AS TIMESTAMPTZ) AS closed_at,
    CAST(status AS VARCHAR) AS status,
    CAST(category AS VARCHAR) AS category,
    CAST(priority AS VARCHAR) AS priority,
    CAST(sentiment AS VARCHAR) AS sentiment,
    TRY_CAST(csat_score AS DOUBLE) AS csat_score
FROM raw_support_tickets;

CREATE OR REPLACE TABLE stg_campaign_exposures AS
SELECT
    CAST(exposure_id AS VARCHAR) AS exposure_id,
    CAST(customer_id AS VARCHAR) AS customer_id,
    CAST(campaign_id AS VARCHAR) AS campaign_id,
    CAST(channel AS VARCHAR) AS channel,
    TRY_CAST(sent_at AS TIMESTAMPTZ) AS sent_at,
    CAST(delivery_status AS VARCHAR) AS delivery_status,
    TRY_CAST(opened_at AS TIMESTAMPTZ) AS opened_at,
    TRY_CAST(clicked_at AS TIMESTAMPTZ) AS clicked_at,
    NULLIF(TRIM(CAST(converted_order_id AS VARCHAR)), '') AS converted_order_id
FROM raw_campaign_exposures;

CREATE OR REPLACE TABLE stg_subscriptions AS
SELECT
    CAST(subscription_id AS VARCHAR) AS subscription_id,
    CAST(customer_id AS VARCHAR) AS customer_id,
    CAST(subscription_type AS VARCHAR) AS subscription_type,
    CAST(status AS VARCHAR) AS status,
    TRY_CAST(started_at AS TIMESTAMPTZ) AS started_at,
    TRY_CAST(ended_at AS TIMESTAMPTZ) AS ended_at,
    TRY_CAST(renewal_at AS TIMESTAMPTZ) AS renewal_at
FROM raw_subscriptions;

CREATE OR REPLACE TABLE stg_consent_preferences AS
SELECT
    CAST(consent_id AS VARCHAR) AS consent_id,
    CAST(customer_id AS VARCHAR) AS customer_id,
    CAST(channel AS VARCHAR) AS channel,
    CAST(status AS VARCHAR) AS status,
    TRY_CAST(updated_at AS TIMESTAMPTZ) AS updated_at,
    CAST(source AS VARCHAR) AS source
FROM raw_consent_preferences;
