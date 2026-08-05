{{
    source_contract_row(
        'customers',
        'BRZ_OLIST_CUSTOMERS_RAW',
        'olist_customers_dataset.csv',
        'customer_id',
        1
    )
}}
union all
{{
    source_contract_row(
        'geolocation',
        'BRZ_OLIST_GEOLOCATION_RAW',
        'olist_geolocation_dataset.csv',
        'source_row_number',
        2
    )
}}
union all
{{
    source_contract_row(
        'order_items',
        'BRZ_OLIST_ORDER_ITEMS_RAW',
        'olist_order_items_dataset.csv',
        'order_id + order_item_id',
        3
    )
}}
union all
{{
    source_contract_row(
        'order_payments',
        'BRZ_OLIST_ORDER_PAYMENTS_RAW',
        'olist_order_payments_dataset.csv',
        'order_id + payment_sequential',
        4
    )
}}
union all
{{
    source_contract_row(
        'order_reviews',
        'BRZ_OLIST_ORDER_REVIEWS_RAW',
        'olist_order_reviews_dataset.csv',
        'review_id + order_id',
        5
    )
}}
union all
{{
    source_contract_row(
        'orders',
        'BRZ_OLIST_ORDERS_RAW',
        'olist_orders_dataset.csv',
        'order_id',
        6
    )
}}
union all
{{
    source_contract_row(
        'products',
        'BRZ_OLIST_PRODUCTS_RAW',
        'olist_products_dataset.csv',
        'product_id',
        7
    )
}}
union all
{{
    source_contract_row(
        'sellers',
        'BRZ_OLIST_SELLERS_RAW',
        'olist_sellers_dataset.csv',
        'seller_id',
        8
    )
}}
union all
{{
    source_contract_row(
        'category_translation',
        'BRZ_PRODUCT_CATEGORY_TRANSLATION_RAW',
        'product_category_name_translation.csv',
        'product_category_name',
        9
    )
}}
