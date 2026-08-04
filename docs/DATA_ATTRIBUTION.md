# Data attribution and use boundary

## Primary dataset

ReviewLens uses the **Brazilian E-Commerce Public Dataset by Olist**, obtained
from [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) on
2026-08-05. The downloaded snapshot contains nine relational CSV files covering
orders, customers, order items, payments, reviews, products, sellers,
geolocation and product-category translation.

The source dataset is licensed under
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International
(CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/).

## Obligations applied by this project

- **Attribution:** public documentation and derived public artifacts identify
  Olist, the dataset title, source link and license link.
- **NonCommercial:** ReviewLens is a personal educational/portfolio project and
  the Olist-backed demo or derived dataset will not be sold or used commercially.
- **ShareAlike:** any distributed adaptation of the source data must use the
  same or a compatible license. Source code has its own repository license;
  that does not relicense the Olist data.
- **Indication of changes:** ReviewLens may validate, normalize, join, aggregate,
  translate category labels and add AI-generated annotations. Those outputs are
  modifications made by ReviewLens, not original Olist fields.
- **No endorsement:** Olist does not sponsor, approve or endorse ReviewLens.

## Privacy and publishing boundary

The license does not remove privacy, contractual or provider-processing risk.
Raw CSVs, review comments, row-level warehouse exports, embeddings and vector
stores remain private and outside Git. Public evidence uses aggregate metrics,
redacted screenshots or synthetic Olist-shaped fixtures. Sending review text to
OpenRouter requires a documented field-minimization and privacy scan first.

The exact local snapshot is recorded by filename, header, row count, byte size
and SHA-256 in [OLIST_SOURCE_MANIFEST.md](data/OLIST_SOURCE_MANIFEST.md).
