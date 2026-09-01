# Automotive Sales & Service Operations Analytics — Business Requirements

## 1. Document purpose and scope

This document defines the business requirements for an analytics platform covering automotive vehicle sales, inventory, service operations, and customer value. It is the business contract for later data modeling, ETL, API, orchestration, and Power BI work; it does not prescribe or implement those components.

### In scope

- Vehicle sales performance by time, dealership, geography, vehicle, salesperson, customer, and channel.
- Inventory position, value, aging, movement, and slow-moving stock.
- Service revenue and repair-order completion performance.
- Customer acquisition, retention, repeat behavior, and lifetime value.
- Executive and operational dashboards with consistent filters and drill-through paths.

### Out of scope for this phase

- Database schemas or SQL objects.
- ETL pipelines, source ingestion, or data-quality code.
- Airflow DAGs, FastAPI endpoints, Docker services, or Power BI files.
- Predictive models, prescriptive pricing, or automated customer outreach.
- Finance-led statutory reporting, tax reporting, and full general-ledger reconciliation.

## 2. Business problem

Sales, inventory, service, and customer data are often held in separate dealer-management, CRM, finance, and operational systems. This fragmentation prevents leaders from seeing a consistent view of revenue and profitability, identifying aging inventory early, measuring service execution, and understanding long-term customer value. Teams need governed definitions and connected reporting that supports both executive monitoring and transaction-level investigation.

## 3. Business objectives

1. Establish a single, agreed view of sales, inventory, service, and customer performance.
2. Monitor revenue, volume, pricing, gross profit, and margin against comparable periods and targets.
3. Reduce working capital tied up in aging and slow-moving vehicle inventory.
4. Improve service throughput, completion performance, and service revenue visibility.
5. Measure repeat purchasing and customer lifetime value across sales and service interactions.
6. Enable users to move from enterprise KPIs to dealership, vehicle, customer, and transaction details.
7. Make every KPI traceable to a definition, grain, time basis, inclusion rule, and data owner.

## 4. Stakeholders and users

| User group | Primary needs |
|---|---|
| Executive leadership | Enterprise trends, target attainment, profitability, risk, and exceptions |
| Sales leadership | Units, revenue, ASP, gross profit, salesperson/dealership performance, and mix |
| Inventory managers | On-hand units, inventory value, aging, turn risk, and slow-moving vehicles |
| Service leadership | Repair-order volume, service revenue, completion rate, and turnaround performance |
| Marketing and CRM | New versus repeat customers, segments, retention, and customer lifetime value |
| Finance and analysts | Reconciled metrics, consistent formulas, data lineage, and exportable detail |

## 5. Cross-functional business rules

- Reporting currency must be configurable; monetary values must use a consistent currency conversion policy when multiple currencies exist.
- Reporting dates must use the dealership's local date while preserving source timestamps and time zones.
- A completed vehicle sale is included on the finalized invoice or delivery date, as agreed with Finance. Quotes, test drives, voided transactions, and fully cancelled sales are excluded.
- Returns must reverse the original sale's units, revenue, cost, and gross profit in the return period unless Finance requires restatement.
- Discounts reduce revenue. Taxes, registration fees, and pass-through government fees are excluded unless Finance approves their inclusion.
- Internal service work and warranty work must be separately identifiable. Their inclusion in service revenue must be controlled by an explicit reporting rule.
- Personally identifiable customer fields must be restricted to authorized users; dashboards should use a stable customer identifier by default.
- Targets and thresholds must be stored by effective period and organizational level rather than embedded in reports.
- All summary metrics must reconcile to permitted transaction detail for the same filters and as-of time.

## 6. Functional requirements

### 6.1 Sales requirements

| ID | Requirement |
|---|---|
| SAL-01 | Report finalized vehicle sales at transaction and vehicle-line grain. |
| SAL-02 | Analyze Revenue, Units Sold, ASP, Gross Profit, and Gross Margin by day, week, month, quarter, and year. |
| SAL-03 | Compare current performance with prior period, prior year, budget, and target where available. |
| SAL-04 | Segment results by dealership, region, salesperson, channel, customer type, vehicle condition, make, model, model year, body type, and fuel type. |
| SAL-05 | Separate new, used, fleet, retail, and other agreed sales channels without double counting. |
| SAL-06 | Show discounts, vehicle cost, and gross-profit contribution and flag zero or negative-margin sales. |
| SAL-07 | Provide transaction-level drill-through to invoice, vehicle, customer identifier, salesperson, sale date, revenue, cost, and gross profit. |

### 6.2 Inventory requirements

| ID | Requirement |
|---|---|
| INV-01 | Report vehicle inventory as of any supported snapshot date at VIN or stock-item grain. |
| INV-02 | Show on-hand units, Inventory Value, Days in Inventory, and Slow-Moving Inventory. |
| INV-03 | Analyze inventory by dealership, location, status, vehicle condition, make, model, model year, body type, fuel type, and acquisition source. |
| INV-04 | Group inventory into configurable aging bands such as 0–30, 31–60, 61–90, and 91+ days. |
| INV-05 | Distinguish available, reserved, in-transit, demonstrator, sold-not-delivered, and unavailable stock. |
| INV-06 | Display aging and value trends from periodic snapshots; historical reports must not reconstruct inventory using only today's state. |
| INV-07 | Drill through from aging bands or slow-moving counts to individual vehicles, acquisition date, cost, status, and age. |

### 6.3 Service requirements

| ID | Requirement |
|---|---|
| SVC-01 | Report repair orders at repair-order header and service-line grain without duplicating header-level amounts. |
| SVC-02 | Show Service Revenue, opened orders, completed orders, Completion Rate, average repair-order value, and turnaround time. |
| SVC-03 | Segment service performance by dealership, advisor, technician, service type, labor/parts category, warranty/customer-pay/internal category, and vehicle. |
| SVC-04 | Track opened, promised, completed, invoiced, cancelled, and reopened statuses using defined status timestamps. |
| SVC-05 | Compare actual completion with promised completion and identify overdue open repair orders. |
| SVC-06 | Drill through to repair-order details, service lines, status history, vehicle, customer identifier, advisor, technician, and monetary amounts. |

### 6.4 Customer requirements

| ID | Requirement |
|---|---|
| CUS-01 | Provide a deduplicated customer view based on an approved survivorship and identity-resolution policy. |
| CUS-02 | Classify customers as new or repeat for a selected period using transactions that occurred before the current qualifying transaction. |
| CUS-03 | Show unique customers, Repeat Customers, repeat-customer rate, purchase frequency, recency, and Customer Lifetime Value. |
| CUS-04 | Combine eligible sales and service activity at customer level while retaining the ability to report each revenue stream separately. |
| CUS-05 | Segment customers by geography, acquisition channel, customer type, first-transaction cohort, vehicle ownership, and value band. |
| CUS-06 | Support cohort analysis from first qualifying transaction through subsequent sales and service activity. |
| CUS-07 | Restrict personal data by role and allow analysis using masked or surrogate identifiers. |

## 7. Business questions

### Sales

- How are Revenue, Units Sold, ASP, Gross Profit, and Gross Margin trending?
- Which dealerships, salespeople, channels, and vehicle categories drive growth or decline?
- Which vehicle sales have negative or unusually low margins?
- How does performance compare with the prior period, prior year, and target?

### Inventory

- How many vehicles are on hand, what is their Inventory Value, and how has that changed?
- Which dealerships, models, and individual vehicles have the highest Days in Inventory?
- How much Slow-Moving Inventory exists by unit count and value?
- Where is capital concentrated, and which aging bands require action?

### Service

- How much Service Revenue is generated, and from which service and payer categories?
- What is the Completion Rate, and which dealerships or teams are below target?
- How many repair orders are overdue relative to their promised completion time?
- Which vehicles and customers return for service after a sale?

### Customer

- How many customers are new versus repeat, and what is the repeat-customer rate?
- Which cohorts, channels, and segments have the highest Customer Lifetime Value?
- How do sales and service revenue contribute to customer value?
- Which high-value customers have become inactive?

## 8. KPI catalog and formulas

The semantic layer must implement these formulas consistently. `SUM`, `COUNT`, and `DISTINCTCOUNT` operate within the active report filters unless a formula explicitly states otherwise. Currency, date, status, cancellation, and return rules in Section 5 apply to every KPI.

| KPI | Business definition and formula | Grain/time basis | Key exclusions or notes |
|---|---|---|---|
| Revenue | Net recognized vehicle-sales revenue. **Revenue = SUM(vehicle sale price − discounts − returns/allowances)** | Finalized sale lines in selected period | Excludes tax, registration, pass-through fees, cancelled/voided sales; finance products shown separately unless approved |
| Units Sold | Net number of vehicles sold. **Units Sold = completed sale units − returned/cancelled-after-completion units** | Distinct finalized vehicle-sale lines in selected period | A vehicle sold as one unit must not be multiplied by payment, trade-in, or accessory rows |
| Average Selling Price (ASP) | Average net vehicle revenue per net unit. **ASP = Revenue / Units Sold** | Selected period and filters | Return blank when Units Sold is zero |
| Gross Profit | Profit before operating expenses. **Gross Profit = Revenue − Cost of Vehicles Sold** | Finalized sales in selected period | Vehicle cost policy must define acquisition cost and approved reconditioning/freight allocations |
| Gross Margin | Gross profit as a share of revenue. **Gross Margin % = Gross Profit / Revenue × 100** | Selected period and filters | Return blank when Revenue is zero; do not average row-level margin percentages |
| Inventory Value | Capital value of eligible vehicles on hand. **Inventory Value = SUM(current approved inventory carrying cost)** | Inventory snapshot as of selected date | Excludes sold/delivered, disposed, and other ineligible statuses; value basis must be approved by Finance |
| Days in Inventory | Age of an on-hand vehicle. **Vehicle Days in Inventory = snapshot date − inventory acquisition/received date**; portfolio average is **SUM(vehicle days) / on-hand units** | Per vehicle at selected snapshot; aggregated as weighted average | Never use future dates; document treatment of transfers so age is not reset unless policy requires it |
| Slow-Moving Inventory | Eligible on-hand vehicles above the configured age threshold. **Slow-Moving Units = COUNTDISTINCT(VIN/stock ID where Days in Inventory > threshold)**; **Slow-Moving Value = SUM(carrying cost for those vehicles)** | Selected snapshot date | Default threshold: more than 90 days; user-visible and configurable; report both units and value |
| Service Revenue | Net recognized revenue from eligible completed/invoiced service lines. **Service Revenue = SUM(labor revenue + parts revenue + approved fees − service discounts − refunds)** | Completed/invoiced service lines in selected period | Taxes excluded; warranty/internal categories must remain separately filterable and follow approved recognition rules |
| Completion Rate | Share of eligible repair orders completed. **Completion Rate % = distinct completed repair orders / distinct eligible repair orders due or closed in period × 100** | Selected reporting period | Eligibility must use one approved denominator (recommended: orders with promised completion date in period); cancelled orders excluded; reopened orders counted once by repair-order ID |
| Repeat Customers | Customers with a qualifying transaction in the selected period and at least one qualifying transaction before their current qualifying transaction. **Repeat Customers = DISTINCTCOUNT(qualifying customer IDs meeting repeat rule)** | Customer within selected period, looking back across available history | Anonymous/unresolved customers excluded; qualifying transactions include finalized vehicle sales and eligible completed service orders unless filtered to one stream |
| Repeat Customer Rate | Share of active identified customers who are repeat. **Repeat Customer Rate % = Repeat Customers / distinct qualifying customers × 100** | Selected period | Return blank when there are no qualifying customers |
| Customer Lifetime Value (historical CLV) | Cumulative realized gross value from an identified customer. **Historical CLV = cumulative vehicle Gross Profit + cumulative service gross profit** | Customer, from first qualifying transaction through selected as-of date | Preferred definition uses gross profit; until reliable service cost exists, show a clearly labeled interim revenue-based CLV: cumulative Sales Revenue + Service Revenue; never mix the two definitions |

### Supporting metrics

- **On-Hand Units:** distinct eligible VINs or stock IDs at the selected inventory snapshot.
- **Average Repair Order Value:** Service Revenue / distinct completed or invoiced repair orders.
- **Average Turnaround Time:** average elapsed hours between repair-order open and completion timestamps for completed orders.
- **Overdue Open Orders:** distinct open repair orders whose promised completion timestamp is before the reporting timestamp.
- **Customer Recency:** days between the as-of date and the customer's most recent qualifying transaction.
- **Purchase Frequency:** count of distinct qualifying transactions per identified customer in the selected observation window.

## 9. Analytical facts and grain

These are conceptual analytical facts, not database table specifications.

| Fact | Required grain | Core measures/events |
|---|---|---|
| Vehicle Sales | One finalized vehicle line per sale/invoice | Sale price, discount, net revenue, vehicle cost, gross profit, unit indicator, return indicator |
| Inventory Snapshot | One vehicle/stock item per location per snapshot date | On-hand indicator, carrying cost, age in days, inventory status, slow-moving indicator |
| Repair Order | One repair-order header | Open/promised/completed/invoiced timestamps, status, order counts, header totals where valid |
| Service Line | One labor, part, or fee line within a repair order | Quantity, labor/parts/fee revenue, discount, cost when available, net revenue |
| Customer Activity | One qualifying customer event | Event type, event timestamp, revenue, gross profit, customer sequence/return indicator |
| Targets | One KPI target per effective period and applicable organization/scope | Target value, threshold, effective dates, target version |

Fact-to-fact joins must not be used in a way that duplicates measures. Shared dimensions and explicitly tested aggregation paths must connect subject areas.

## 10. Conformed dimensions

| Dimension | Required attributes |
|---|---|
| Date | Date, day, week, month, quarter, year, fiscal periods, working-day indicator |
| Time | Hour and agreed operating-period attributes where intraday analysis is required |
| Dealership/Organization | Dealership, branch, region, market, ownership group, active dates |
| Geography | Country, state/province, city, postal area, market; privacy-appropriate granularity |
| Vehicle | VIN/stock identifier, condition, make, model, trim, model year, body type, fuel type, color |
| Customer | Surrogate customer ID, customer type, value segment, cohort, acquisition channel, geography; protected attributes restricted |
| Employee | Salesperson, advisor, technician, team, role, dealership, effective dates |
| Sales Channel | Retail, fleet, digital, partner, and other governed channels |
| Service | Service category, operation code, labor/part/fee classification, payer category |
| Inventory Status | Available, reserved, in-transit, demonstrator, sold-not-delivered, unavailable, disposed |
| Transaction Status | Business-approved sale and repair-order status categories |
| Aging Band | Configurable lower/upper day boundaries and display order |

Historical reporting must preserve relevant attribute changes through effective dating or another approved history method.

## 11. Dashboard requirements

### Page 1 — Executive Overview

- KPI cards: Revenue, Units Sold, ASP, Gross Profit, Gross Margin, Inventory Value, Slow-Moving Inventory, Service Revenue, Completion Rate, Repeat Customers, and Customer Lifetime Value.
- Trends against prior period, prior year, and target.
- Sales/service contribution and dealership ranking.
- Exception callouts for margin, inventory aging, and service completion.

### Page 2 — Sales Performance

- Revenue, Units Sold, ASP, Gross Profit, and Gross Margin trends.
- Performance by dealership, salesperson, channel, and vehicle hierarchy.
- Price/volume/mix views and low- or negative-margin exceptions.
- Drill-through to sale detail.

### Page 3 — Inventory & Aging

- On-Hand Units, Inventory Value, average Days in Inventory, Slow-Moving Units, and Slow-Moving Value.
- Aging-band distribution by units and value.
- Trends by snapshot date and concentration by dealership and vehicle hierarchy.
- Action list for slow-moving vehicles with individual vehicle drill-through.

### Page 4 — Service Operations

- Service Revenue, repair-order counts, Completion Rate, average repair-order value, turnaround time, and overdue open orders.
- Trends and comparisons by dealership, advisor, technician, service category, and payer type.
- Open/overdue workload and repair-order drill-through.

### Page 5 — Customer & Retention

- Active customers, Repeat Customers, repeat-customer rate, recency, frequency, and Customer Lifetime Value.
- New-versus-repeat trends, cohort retention, value segments, and sales-versus-service contribution.
- Drill-through to privacy-appropriate customer history.

### Page 6 — Detail & Data Quality

- Exportable, permission-aware transaction detail for reconciliation.
- Refresh timestamp, latest source date, row counts, rejected/quarantined counts, and quality exceptions.
- KPI definition tooltips or links back to the governed catalog.

## 12. Global filters and interactions

All applicable pages must support:

- Reporting date range and comparison period.
- Inventory snapshot/as-of date on inventory visuals.
- Region, market, dealership, and location.
- Vehicle condition, make, model, model year, body type, and fuel type.
- Sales channel and customer type.
- Salesperson, service advisor, and technician where relevant.
- Inventory status and aging band.
- Service type, payer category, and repair-order status.
- New versus repeat customer and customer value segment.
- Configurable slow-moving threshold, defaulting to more than 90 days.

Filters must cascade to valid values, clearly show active selections, support a one-click reset, and avoid silently applying unrelated filters. Metric cards and detail totals must reconcile under identical filters.

## 13. Drill-through requirements

| Source context | Drill-through destination | Required context and detail |
|---|---|---|
| Executive KPI or dealership | Dealership performance | Date, dealership, comparison period, target, sales, inventory, service, and customer summary |
| Sales visual | Sale detail | Invoice/sale ID, date, dealership, vehicle, masked customer ID, salesperson, channel, revenue, cost, gross profit |
| Inventory aging or vehicle visual | Vehicle inventory detail | VIN/stock ID, vehicle attributes, location, acquisition date, Days in Inventory, carrying cost, status, snapshot date |
| Service visual | Repair-order detail | Repair-order ID, dates/statuses, vehicle, masked customer ID, advisor, technician, service lines, revenue |
| Customer visual | Customer history | Masked/surrogate customer ID, cohort, vehicle purchases, service visits, recency, frequency, historical CLV components |

Drill-through must preserve the originating filters, provide a clear back action, use role-based security, and allow authorized export without exposing restricted personal data.

## 14. Data quality, governance, and non-functional requirements

- **Uniqueness:** sale-line, VIN/stock snapshot, repair-order, service-line, and customer identifiers must satisfy their defined grain.
- **Completeness:** required dates, organizational keys, status, monetary values, and relationship keys must be monitored.
- **Validity:** timestamps must follow logical order; monetary and quantity exceptions must be flagged; status values must map to governed categories.
- **Reconciliation:** Revenue, Gross Profit, Inventory Value, and Service Revenue must reconcile to approved source totals within documented tolerances.
- **Freshness:** each dashboard must display its refresh time and latest included business date. Refresh service-level objectives will be agreed with source owners before implementation.
- **Security:** least-privilege access, row-level organizational security, and protected customer attributes are required.
- **Performance:** common summary pages should respond within five seconds under normal load; drill-through pages should respond within ten seconds, subject to agreed capacity tests.
- **Auditability:** metric definitions, lineage, threshold changes, target versions, and data-quality exceptions must be traceable.
- **Accessibility:** reports must not rely on color alone and must use readable labels, meaningful alt text, and keyboard-compatible navigation where supported.

## 15. Assumptions and decisions required before implementation

1. Finance will approve revenue recognition, vehicle cost, return treatment, currency conversion, and inventory valuation rules.
2. Service leadership will approve the Completion Rate denominator and treatment of warranty and internal work.
3. The business will approve the default slow-moving threshold and whether it varies by vehicle class or dealership.
4. Customer-data owners will approve identity-resolution, qualifying-event, privacy, and retention rules.
5. Service cost must be reliable before gross-profit-based CLV becomes authoritative; until then, revenue-based CLV must be labeled as interim.
6. Source owners will confirm historical inventory snapshots, target availability, fiscal calendar, and source refresh frequency.

## 16. Acceptance criteria and completeness review

This requirements phase is complete when:

- Business owners for Sales, Inventory, Service, Customer/CRM, and Finance approve the definitions and unresolved decisions.
- Every requested KPI has a formula, grain/time basis, inclusion/exclusion behavior, and zero-denominator treatment where applicable.
- Facts have an explicit grain and dimensions support the requested analysis without measure duplication.
- Dashboard pages address executive, sales, inventory, service, customer, detail, and data-quality needs.
- Global filters and drill-through destinations are defined, context-preserving, and privacy-aware.
- Historical/as-of behavior is defined for inventory, customer value, slowly changing attributes, returns, and reopened repair orders.
- Reconciliation, freshness, security, performance, accessibility, and auditability expectations are documented.
- Open assumptions are assigned to an accountable business owner before technical design begins.

### Review checklist

- [x] Business problem, objectives, scope, stakeholders, and shared rules documented.
- [x] Sales, inventory, service, and customer requirements documented.
- [x] Business questions documented for all four domains.
- [x] Revenue, Units Sold, ASP, Gross Profit, Gross Margin, Inventory Value, Days in Inventory, Slow-Moving Inventory, Service Revenue, Completion Rate, Repeat Customers, and Customer Lifetime Value defined.
- [x] Conceptual facts, dimensions, dashboard pages, filters, and drill-through requirements documented.
- [x] Data quality, governance, privacy, non-functional expectations, assumptions, and acceptance criteria documented.
- [x] Database, ETL, API, Airflow, Docker, and Power BI implementation excluded from this phase.

