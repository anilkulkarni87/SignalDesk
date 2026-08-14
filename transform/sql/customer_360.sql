-- Commit 03: final deterministic semantic layer.
--
-- This is intentionally a VIEW. Relative recency fields are derived from
-- absolute timestamps + runtime_context, so advancing as_of_ts does not require
-- rewriting every customer row.

CREATE OR REPLACE VIEW customer_360 AS
SELECT
    c.customer_id,
    ctx.as_of_ts,
    c.created_at AS profile_created_at,
    i.first_seen_at,
    i.last_seen_at,
    DATE_DIFF('day', i.last_seen_at, ctx.as_of_ts) AS days_since_last_seen,
    i.resolved_identity_count,
    c.customer_status,
    c.loyalty_tier,
    c.country,
    c.timezone,

    p.lifetime_orders,
    p.lifetime_value,
    p.orders_30d,
    p.orders_60d,
    p.orders_90d,
    p.orders_prior_60d,
    p.revenue_60d,
    p.revenue_prior_60d,
    CASE
        WHEN p.last_purchase_at IS NULL THEN NULL
        ELSE DATE_DIFF('day', p.last_purchase_at, ctx.as_of_ts)
    END AS days_since_purchase,
    p.avg_order_value_lifetime,
    p.refund_rate_90d,
    p.purchase_change_pct,
    p.preferred_category,
    p.purchase_decline_flag,

    e.sessions_30d,
    e.sessions_60d,
    e.sessions_90d,
    e.sessions_prior_60d,
    e.session_change_pct,
    e.product_views_60d,
    e.add_to_cart_60d,
    e.checkout_starts_60d,
    e.channel_affinity,
    e.engagement_decline_flag,

    s.support_cases_lifetime,
    s.support_cases_90d,
    s.open_support_cases,
    s.negative_support_cases_90d,
    s.high_priority_support_cases_90d,
    CASE
        WHEN s.last_support_case_at IS NULL THEN NULL
        ELSE DATE_DIFF('day', s.last_support_case_at, ctx.as_of_ts)
    END AS days_since_last_support_case,
    s.avg_csat_90d,
    s.support_attention_flag,

    m.campaigns_delivered_90d,
    m.email_delivered_90d,
    m.email_opens_90d,
    m.email_clicks_90d,
    m.email_open_rate_90d,
    m.email_click_rate_90d,
    m.email_engagement,
    CASE
        WHEN m.last_campaign_at IS NULL THEN NULL
        ELSE DATE_DIFF('day', m.last_campaign_at, ctx.as_of_ts)
    END AS days_since_last_campaign,

    su.active_subscription_count,
    su.recent_subscription_cancellation_flag,

    co.email_opted_in,
    co.sms_opted_in,
    co.push_opted_in

FROM stg_customers c
CROSS JOIN runtime_context ctx
JOIN int_customer_identity_features i USING (customer_id)
JOIN int_customer_purchase_features p USING (customer_id)
JOIN int_customer_engagement_features e USING (customer_id)
JOIN int_customer_support_features s USING (customer_id)
JOIN int_customer_campaign_features m USING (customer_id)
JOIN int_customer_subscription_features su USING (customer_id)
JOIN int_customer_consent_features co USING (customer_id);
