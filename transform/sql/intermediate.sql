-- Commit 03: incremental-aware domain feature marts.
--
-- feature_customers controls the population being recomputed:
--   full build        -> all stg_customers
--   incremental patch -> only affected customers
--
-- Absolute timestamps are materialized in marts. Volatile "days since" values
-- are computed in the final customer_360 view so advancing as_of_ts does not
-- force all customers to be rewritten.

CREATE OR REPLACE TABLE int_customer_identity_features AS
WITH identity_rollup AS (
    SELECT
        i.customer_id,
        COUNT(*) AS resolved_identity_count,
        MIN(i.first_seen_at) AS first_seen_at,
        MAX(i.last_seen_at) AS identity_last_seen_at
    FROM stg_identities i
    JOIN feature_customers fc
      ON i.customer_id = fc.customer_id
    WHERE i.customer_id IS NOT NULL
    GROUP BY i.customer_id
),
activity AS (
    SELECT customer_id, MAX(activity_at) AS activity_last_seen_at
    FROM (
        SELECT s.resolved_customer_id AS customer_id, MAX(s.session_started_at) AS activity_at
        FROM stg_sessions s
        JOIN feature_customers fc
          ON s.resolved_customer_id = fc.customer_id
        WHERE s.resolved_customer_id IS NOT NULL
        GROUP BY s.resolved_customer_id

        UNION ALL

        SELECT e.resolved_customer_id AS customer_id, MAX(e.event_timestamp) AS activity_at
        FROM stg_events e
        JOIN feature_customers fc
          ON e.resolved_customer_id = fc.customer_id
        WHERE e.resolved_customer_id IS NOT NULL
        GROUP BY e.resolved_customer_id

        UNION ALL

        SELECT o.customer_id, MAX(o.order_timestamp) AS activity_at
        FROM stg_orders o
        JOIN feature_customers fc USING (customer_id)
        GROUP BY o.customer_id

        UNION ALL

        SELECT t.customer_id, MAX(t.opened_at) AS activity_at
        FROM stg_support_tickets t
        JOIN feature_customers fc USING (customer_id)
        GROUP BY t.customer_id
    ) x
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    COALESCE(i.resolved_identity_count, 0) AS resolved_identity_count,
    COALESCE(i.first_seen_at, c.created_at) AS first_seen_at,
    GREATEST(
        COALESCE(i.identity_last_seen_at, c.created_at),
        COALESCE(a.activity_last_seen_at, c.created_at)
    ) AS last_seen_at
FROM feature_customers c
LEFT JOIN identity_rollup i USING (customer_id)
LEFT JOIN activity a USING (customer_id);

CREATE OR REPLACE TABLE int_customer_preferred_category AS
WITH category_spend AS (
    SELECT
        o.customer_id,
        p.category,
        SUM(oi.line_total) AS category_spend
    FROM stg_orders o
    JOIN feature_customers fc USING (customer_id)
    JOIN stg_order_items oi USING (order_id)
    JOIN stg_products p USING (product_id)
    WHERE o.status IN ('COMPLETED', 'SHIPPED')
    GROUP BY o.customer_id, p.category
)
SELECT customer_id, category AS preferred_category
FROM category_spend
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY category_spend DESC, category ASC
) = 1;

CREATE OR REPLACE TABLE int_customer_purchase_features AS
WITH ctx AS (
    SELECT as_of_ts FROM runtime_context
),
agg AS (
    SELECT
        c.customer_id,

        COUNT(o.order_id) FILTER (
            WHERE o.status IN ('COMPLETED', 'SHIPPED')
        ) AS lifetime_orders,

        COALESCE(SUM(o.total_amount) FILTER (
            WHERE o.status IN ('COMPLETED', 'SHIPPED')
        ), 0) AS lifetime_value,

        COUNT(o.order_id) FILTER (
            WHERE o.status IN ('COMPLETED', 'SHIPPED')
              AND o.order_timestamp > ctx.as_of_ts - INTERVAL '30 days'
              AND o.order_timestamp <= ctx.as_of_ts
        ) AS orders_30d,

        COUNT(o.order_id) FILTER (
            WHERE o.status IN ('COMPLETED', 'SHIPPED')
              AND o.order_timestamp > ctx.as_of_ts - INTERVAL '60 days'
              AND o.order_timestamp <= ctx.as_of_ts
        ) AS orders_60d,

        COUNT(o.order_id) FILTER (
            WHERE o.status IN ('COMPLETED', 'SHIPPED')
              AND o.order_timestamp > ctx.as_of_ts - INTERVAL '90 days'
              AND o.order_timestamp <= ctx.as_of_ts
        ) AS orders_90d,

        COUNT(o.order_id) FILTER (
            WHERE o.status IN ('COMPLETED', 'SHIPPED')
              AND o.order_timestamp > ctx.as_of_ts - INTERVAL '120 days'
              AND o.order_timestamp <= ctx.as_of_ts - INTERVAL '60 days'
        ) AS orders_prior_60d,

        COALESCE(SUM(o.total_amount) FILTER (
            WHERE o.status IN ('COMPLETED', 'SHIPPED')
              AND o.order_timestamp > ctx.as_of_ts - INTERVAL '60 days'
              AND o.order_timestamp <= ctx.as_of_ts
        ), 0) AS revenue_60d,

        COALESCE(SUM(o.total_amount) FILTER (
            WHERE o.status IN ('COMPLETED', 'SHIPPED')
              AND o.order_timestamp > ctx.as_of_ts - INTERVAL '120 days'
              AND o.order_timestamp <= ctx.as_of_ts - INTERVAL '60 days'
        ), 0) AS revenue_prior_60d,

        MAX(o.order_timestamp) FILTER (
            WHERE o.status IN ('COMPLETED', 'SHIPPED')
        ) AS last_purchase_at,

        COUNT(o.order_id) FILTER (
            WHERE o.status = 'REFUNDED'
              AND o.order_timestamp > ctx.as_of_ts - INTERVAL '90 days'
              AND o.order_timestamp <= ctx.as_of_ts
        ) AS refunded_orders_90d,

        COUNT(o.order_id) FILTER (
            WHERE o.order_timestamp > ctx.as_of_ts - INTERVAL '90 days'
              AND o.order_timestamp <= ctx.as_of_ts
        ) AS all_orders_90d

    FROM feature_customers c
    CROSS JOIN ctx
    LEFT JOIN stg_orders o USING (customer_id)
    GROUP BY c.customer_id, ctx.as_of_ts
)
SELECT
    a.customer_id,
    a.lifetime_orders,
    ROUND(a.lifetime_value, 2) AS lifetime_value,
    a.orders_30d,
    a.orders_60d,
    a.orders_90d,
    a.orders_prior_60d,
    ROUND(a.revenue_60d, 2) AS revenue_60d,
    ROUND(a.revenue_prior_60d, 2) AS revenue_prior_60d,
    a.last_purchase_at,
    CASE
        WHEN a.lifetime_orders = 0 THEN NULL
        ELSE ROUND(a.lifetime_value / a.lifetime_orders, 2)
    END AS avg_order_value_lifetime,
    CASE
        WHEN a.all_orders_90d = 0 THEN 0
        ELSE ROUND(a.refunded_orders_90d::DOUBLE / a.all_orders_90d, 4)
    END AS refund_rate_90d,
    CASE
        WHEN a.orders_prior_60d = 0 THEN NULL
        ELSE ROUND(
            (a.orders_60d - a.orders_prior_60d)::DOUBLE
            / a.orders_prior_60d,
            4
        )
    END AS purchase_change_pct,
    pc.preferred_category,
    (
        a.orders_prior_60d >= 2
        AND a.orders_60d < a.orders_prior_60d
    ) AS purchase_decline_flag
FROM agg a
LEFT JOIN int_customer_preferred_category pc USING (customer_id);

CREATE OR REPLACE TABLE int_customer_channel_affinity AS
WITH ctx AS (SELECT as_of_ts FROM runtime_context),
channel_counts AS (
    SELECT
        s.resolved_customer_id AS customer_id,
        s.channel,
        COUNT(*) AS sessions
    FROM stg_sessions s
    JOIN feature_customers fc
      ON s.resolved_customer_id = fc.customer_id
    CROSS JOIN ctx
    WHERE s.resolved_customer_id IS NOT NULL
      AND s.session_started_at > ctx.as_of_ts - INTERVAL '90 days'
      AND s.session_started_at <= ctx.as_of_ts
    GROUP BY s.resolved_customer_id, s.channel
)
SELECT customer_id, channel AS channel_affinity
FROM channel_counts
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY sessions DESC, channel ASC
) = 1;

CREATE OR REPLACE TABLE int_customer_engagement_features AS
WITH ctx AS (
    SELECT as_of_ts FROM runtime_context
),
sessions AS (
    SELECT
        c.customer_id,
        COUNT(s.session_id) FILTER (
            WHERE s.session_started_at > ctx.as_of_ts - INTERVAL '30 days'
              AND s.session_started_at <= ctx.as_of_ts
        ) AS sessions_30d,
        COUNT(s.session_id) FILTER (
            WHERE s.session_started_at > ctx.as_of_ts - INTERVAL '60 days'
              AND s.session_started_at <= ctx.as_of_ts
        ) AS sessions_60d,
        COUNT(s.session_id) FILTER (
            WHERE s.session_started_at > ctx.as_of_ts - INTERVAL '90 days'
              AND s.session_started_at <= ctx.as_of_ts
        ) AS sessions_90d,
        COUNT(s.session_id) FILTER (
            WHERE s.session_started_at > ctx.as_of_ts - INTERVAL '120 days'
              AND s.session_started_at <= ctx.as_of_ts - INTERVAL '60 days'
        ) AS sessions_prior_60d
    FROM feature_customers c
    CROSS JOIN ctx
    LEFT JOIN stg_sessions s
        ON c.customer_id = s.resolved_customer_id
    GROUP BY c.customer_id, ctx.as_of_ts
),
events AS (
    SELECT
        c.customer_id,
        COUNT(e.event_id) FILTER (
            WHERE e.event_type = 'product_view'
              AND e.event_timestamp > ctx.as_of_ts - INTERVAL '60 days'
              AND e.event_timestamp <= ctx.as_of_ts
        ) AS product_views_60d,
        COUNT(e.event_id) FILTER (
            WHERE e.event_type = 'add_to_cart'
              AND e.event_timestamp > ctx.as_of_ts - INTERVAL '60 days'
              AND e.event_timestamp <= ctx.as_of_ts
        ) AS add_to_cart_60d,
        COUNT(e.event_id) FILTER (
            WHERE e.event_type = 'checkout_started'
              AND e.event_timestamp > ctx.as_of_ts - INTERVAL '60 days'
              AND e.event_timestamp <= ctx.as_of_ts
        ) AS checkout_starts_60d
    FROM feature_customers c
    CROSS JOIN ctx
    LEFT JOIN stg_events e
        ON c.customer_id = e.resolved_customer_id
    GROUP BY c.customer_id, ctx.as_of_ts
)
SELECT
    s.customer_id,
    s.sessions_30d,
    s.sessions_60d,
    s.sessions_90d,
    s.sessions_prior_60d,
    CASE
        WHEN s.sessions_prior_60d = 0 THEN NULL
        ELSE ROUND(
            (s.sessions_60d - s.sessions_prior_60d)::DOUBLE
            / s.sessions_prior_60d,
            4
        )
    END AS session_change_pct,
    e.product_views_60d,
    e.add_to_cart_60d,
    e.checkout_starts_60d,
    ca.channel_affinity,
    (
        s.sessions_prior_60d >= 2
        AND s.sessions_60d < s.sessions_prior_60d
    ) AS engagement_decline_flag
FROM sessions s
JOIN events e USING (customer_id)
LEFT JOIN int_customer_channel_affinity ca USING (customer_id);

CREATE OR REPLACE TABLE int_customer_support_features AS
WITH ctx AS (SELECT as_of_ts FROM runtime_context)
SELECT
    c.customer_id,
    COUNT(t.ticket_id) AS support_cases_lifetime,
    COUNT(t.ticket_id) FILTER (
        WHERE t.opened_at > ctx.as_of_ts - INTERVAL '90 days'
          AND t.opened_at <= ctx.as_of_ts
    ) AS support_cases_90d,
    COUNT(t.ticket_id) FILTER (
        WHERE t.status IN ('OPEN', 'PENDING')
    ) AS open_support_cases,
    COUNT(t.ticket_id) FILTER (
        WHERE t.sentiment = 'NEGATIVE'
          AND t.opened_at > ctx.as_of_ts - INTERVAL '90 days'
          AND t.opened_at <= ctx.as_of_ts
    ) AS negative_support_cases_90d,
    COUNT(t.ticket_id) FILTER (
        WHERE t.priority IN ('HIGH', 'URGENT')
          AND t.opened_at > ctx.as_of_ts - INTERVAL '90 days'
          AND t.opened_at <= ctx.as_of_ts
    ) AS high_priority_support_cases_90d,
    MAX(t.opened_at) AS last_support_case_at,
    ROUND(AVG(t.csat_score) FILTER (
        WHERE t.opened_at > ctx.as_of_ts - INTERVAL '90 days'
          AND t.opened_at <= ctx.as_of_ts
    ), 3) AS avg_csat_90d,
    (
        COUNT(t.ticket_id) FILTER (WHERE t.status IN ('OPEN', 'PENDING')) > 0
        OR
        COUNT(t.ticket_id) FILTER (
            WHERE t.sentiment = 'NEGATIVE'
              AND t.opened_at > ctx.as_of_ts - INTERVAL '90 days'
              AND t.opened_at <= ctx.as_of_ts
        ) >= 2
    ) AS support_attention_flag
FROM feature_customers c
CROSS JOIN ctx
LEFT JOIN stg_support_tickets t USING (customer_id)
GROUP BY c.customer_id, ctx.as_of_ts;

CREATE OR REPLACE TABLE int_customer_campaign_features AS
WITH ctx AS (SELECT as_of_ts FROM runtime_context),
agg AS (
    SELECT
        c.customer_id,
        COUNT(e.exposure_id) FILTER (
            WHERE e.delivery_status = 'DELIVERED'
              AND e.sent_at > ctx.as_of_ts - INTERVAL '90 days'
              AND e.sent_at <= ctx.as_of_ts
        ) AS campaigns_delivered_90d,
        COUNT(e.exposure_id) FILTER (
            WHERE e.channel = 'EMAIL'
              AND e.delivery_status = 'DELIVERED'
              AND e.sent_at > ctx.as_of_ts - INTERVAL '90 days'
              AND e.sent_at <= ctx.as_of_ts
        ) AS email_delivered_90d,
        COUNT(e.exposure_id) FILTER (
            WHERE e.channel = 'EMAIL'
              AND e.opened_at IS NOT NULL
              AND e.sent_at > ctx.as_of_ts - INTERVAL '90 days'
              AND e.sent_at <= ctx.as_of_ts
        ) AS email_opens_90d,
        COUNT(e.exposure_id) FILTER (
            WHERE e.channel = 'EMAIL'
              AND e.clicked_at IS NOT NULL
              AND e.sent_at > ctx.as_of_ts - INTERVAL '90 days'
              AND e.sent_at <= ctx.as_of_ts
        ) AS email_clicks_90d,
        MAX(e.sent_at) AS last_campaign_at
    FROM feature_customers c
    CROSS JOIN ctx
    LEFT JOIN stg_campaign_exposures e USING (customer_id)
    GROUP BY c.customer_id, ctx.as_of_ts
)
SELECT
    a.customer_id,
    a.campaigns_delivered_90d,
    a.email_delivered_90d,
    a.email_opens_90d,
    a.email_clicks_90d,
    CASE WHEN a.email_delivered_90d = 0 THEN 0
         ELSE ROUND(a.email_opens_90d::DOUBLE / a.email_delivered_90d, 4)
    END AS email_open_rate_90d,
    CASE WHEN a.email_delivered_90d = 0 THEN 0
         ELSE ROUND(a.email_clicks_90d::DOUBLE / a.email_delivered_90d, 4)
    END AS email_click_rate_90d,
    CASE
        WHEN a.email_delivered_90d = 0 THEN 'NO_RECENT_EMAIL'
        WHEN a.email_clicks_90d > 0 THEN 'CLICKED'
        WHEN a.email_opens_90d > 0 THEN 'OPENED'
        ELSE 'DELIVERED_NO_ENGAGEMENT'
    END AS email_engagement,
    a.last_campaign_at
FROM agg a;

CREATE OR REPLACE TABLE int_customer_subscription_features AS
WITH ctx AS (SELECT as_of_ts FROM runtime_context)
SELECT
    c.customer_id,
    COUNT(s.subscription_id) FILTER (
        WHERE s.status = 'ACTIVE'
    ) AS active_subscription_count,
    (
        COUNT(s.subscription_id) FILTER (
            WHERE s.status = 'CANCELED'
              AND s.ended_at > ctx.as_of_ts - INTERVAL '90 days'
              AND s.ended_at <= ctx.as_of_ts
        ) > 0
    ) AS recent_subscription_cancellation_flag
FROM feature_customers c
CROSS JOIN ctx
LEFT JOIN stg_subscriptions s USING (customer_id)
GROUP BY c.customer_id, ctx.as_of_ts;

CREATE OR REPLACE TABLE int_customer_consent_features AS
WITH ranked AS (
    SELECT
        cp.customer_id,
        cp.channel,
        cp.status,
        cp.updated_at,
        cp.consent_id,
        ROW_NUMBER() OVER (
            PARTITION BY cp.customer_id, cp.channel
            ORDER BY cp.updated_at DESC, cp.consent_id DESC
        ) AS rn
    FROM stg_consent_preferences cp
    JOIN feature_customers fc USING (customer_id)
),
latest AS (
    SELECT customer_id, channel, status
    FROM ranked
    WHERE rn = 1
)
SELECT
    c.customer_id,
    COALESCE(MAX(CASE WHEN l.channel = 'EMAIL' THEN l.status = 'OPTED_IN' END), FALSE)
        AS email_opted_in,
    COALESCE(MAX(CASE WHEN l.channel = 'SMS' THEN l.status = 'OPTED_IN' END), FALSE)
        AS sms_opted_in,
    COALESCE(MAX(CASE WHEN l.channel = 'PUSH' THEN l.status = 'OPTED_IN' END), FALSE)
        AS push_opted_in
FROM feature_customers c
LEFT JOIN latest l USING (customer_id)
GROUP BY c.customer_id;
