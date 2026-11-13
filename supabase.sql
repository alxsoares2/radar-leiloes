begin;

create table if not exists public.radar_snapshot (
  id text primary key check (id = 'main'),
  payload jsonb not null
);

create table if not exists public.radar_price_history (
  lot_id text not null,
  observed_at timestamptz not null,
  price numeric not null,
  primary key (lot_id, observed_at)
);

alter table public.radar_snapshot enable row level security;
alter table public.radar_price_history enable row level security;
revoke all on public.radar_snapshot, public.radar_price_history from public, anon, authenticated;
grant select, insert, update on public.radar_snapshot to service_role;
grant select, insert on public.radar_price_history to service_role;

create or replace function public.radar_capture_prices()
returns trigger language plpgsql set search_path = '' as $$
declare
  previous jsonb;
begin
  if tg_op = 'UPDATE' then
    previous := old.payload;
  end if;
  insert into public.radar_price_history (lot_id, observed_at, price)
  select lot ->> 'id', now(), (lot ->> 'price')::numeric
  from jsonb_array_elements(new.payload -> 'lots') as incoming(lot)
  where jsonb_typeof(lot -> 'price') = 'number'
    and not exists (
      select 1 from jsonb_array_elements(coalesce(previous -> 'lots', '[]'::jsonb)) as prior(item)
      where item ->> 'id' = lot ->> 'id' and item -> 'price' = lot -> 'price'
    )
  on conflict do nothing;
  return new;
end;
$$;

drop trigger if exists radar_snapshot_price_change on public.radar_snapshot;
create trigger radar_snapshot_price_change after insert or update on public.radar_snapshot
for each row execute function public.radar_capture_prices();

commit;

