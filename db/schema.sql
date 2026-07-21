create extension if not exists postgis;

create table if not exists units (
  id              text primary key,
  name            text not null,
  type            text not null check (type in ('county','township','municipality','special_district')),
  county          text not null default 'Cook',
  website         text,
  fy_start        text,
  geom            geometry(MultiPolygon, 4326),
  ioc_code        text,
  agenda_platform text,
  packet_url      text,
  population      int,
  as_of           date not null
);
create index if not exists units_geom_idx on units using gist (geom);
create index if not exists units_type_idx on units (type);

create table if not exists documents (
  id             serial primary key,
  unit_id        text references units,
  kind           text,
  url            text not null,
  fetched_at     timestamptz,
  extracted_text text,
  pages          int
);
create unique index if not exists documents_url_idx on documents (url);

create table if not exists officials (
  id         serial primary key,
  unit_id    text references units,
  role       text not null,
  name       text not null,
  email      text,
  phone      text,
  term_end   date,
  certainty  text not null check (certainty in ('verified','extracted','stale_risk')),
  source_url text not null,
  as_of      date not null
);
create index if not exists officials_unit_idx on officials (unit_id);

create table if not exists afr_summaries (
  unit_id            text references units,
  fiscal_year        int,
  total_revenues     numeric,
  total_expenditures numeric,
  fund_balance       numeric,
  total_debt         numeric,
  fund_detail        jsonb,
  filed_on_time      boolean,
  source_url         text not null,
  primary key (unit_id, fiscal_year)
);

create table if not exists spend_lines (
  id            serial primary key,
  unit_id       text references units,
  meeting_date  date,
  vendor_raw    text not null,
  vendor_canon  text,
  amount        numeric not null,
  fund          text,
  category      text,
  description   text,
  certainty     text not null default 'extracted',
  source_doc_id int references documents
);
create index if not exists spend_unit_idx on spend_lines (unit_id);

create table if not exists meetings (
  id             serial primary key,
  unit_id        text references units,
  body           text,
  meeting_ts     timestamptz,
  status         text,
  agenda_doc_id  int references documents,
  minutes_doc_id int references documents
);
create index if not exists meetings_unit_ts_idx on meetings (unit_id, meeting_ts);

create table if not exists agenda_items (
  id         serial primary key,
  meeting_id int references meetings,
  item_no    text,
  title      text,
  topic      text,
  action     text,
  fts        tsvector
);
create index if not exists agenda_fts_idx on agenda_items using gin (fts);

create table if not exists usage_events (
  id          bigserial primary key,
  ts          timestamptz default now(),
  surface     text,
  tool        text,
  unit_id     text,
  params_hash text
);

create table if not exists geocode_cache (
  addr_hash       text primary key,
  input_address   text not null,
  matched_address text not null,
  lat             double precision not null,
  lng             double precision not null,
  created_at      timestamptz default now()
);
