-- Essential tables and indices for Motify (Supabase/Postgres)

create table if not exists users (
  wallet text primary key,
  created_at timestamptz default now()
);

create table if not exists challenges (
  id bigserial primary key,
  owner_wallet text,
  -- Legacy fields (kept for back-compat): title, target_metric, target_value
  title text,
  -- New fields aligned with FE/contract
  name text,
  description text,
  description_hash text,
  contract_address text,
  goal text,
  service_type text,
  activity_type text,
  api_provider text,
  is_charity boolean default false,
  start_at timestamptz not null,
  end_at timestamptz not null,
  charity_wallet text,
  is_private boolean default false,
  invite_code text,
  allowed_wallets text[],
  stake_token text,
  proof_policy jsonb,
  on_chain_challenge_id bigint,
  created_tx_hash text,
  created_block_number bigint,
  completed boolean default false,
  status text default 'pending'
);
create index if not exists idx_challenges_owner on challenges(owner_wallet);
create index if not exists idx_challenges_contract on challenges(contract_address);
create index if not exists idx_challenges_status on challenges(status);
create index if not exists idx_challenges_desc_hash on challenges(description_hash);
create unique index if not exists ux_challenges_contract_onchain_id on challenges(contract_address, on_chain_challenge_id);
-- created_tx_hash index will be created after migration-safe ALTERs below

-- Migration-safe: add new columns on existing deployments
alter table if exists challenges add column if not exists name text;
alter table if exists challenges add column if not exists description text;
alter table if exists challenges add column if not exists description_hash text;
alter table if exists challenges add column if not exists contract_address text;
alter table if exists challenges add column if not exists goal text;
alter table if exists challenges add column if not exists service_type text;
alter table if exists challenges add column if not exists activity_type text;
alter table if exists challenges add column if not exists api_provider text;
alter table if exists challenges add column if not exists is_charity boolean default false;
alter table if exists challenges add column if not exists on_chain_challenge_id bigint;
alter table if exists challenges add column if not exists created_tx_hash text;
alter table if exists challenges add column if not exists created_block_number bigint;
alter table if exists challenges add column if not exists completed boolean default false;
alter table if exists challenges add column if not exists status text default 'pending';

-- Create index on created_tx_hash now that the column exists (on fresh or migrated DBs)
create index if not exists idx_challenges_created_tx on challenges(created_tx_hash);

create table if not exists stakes (
  id bigserial primary key,
  challenge_id bigint not null references challenges(id),
  user_wallet text not null references users(wallet),
  amount_minor_units numeric(78,0) not null, -- token smallest unit (e.g., USDC 6 decimals)
  token_address text,
  decimals int,
  tx_hash_deposit text,
  joined_via text,
  unique (challenge_id, user_wallet)
);

-- Migration-safe: ensure token-agnostic stake amount column exists
alter table if exists stakes add column if not exists amount_minor_units numeric(78,0);

create table if not exists proofs (
  id bigserial primary key,
  challenge_id bigint not null references challenges(id),
  user_wallet text not null references users(wallet),
  provider text not null,
  metric text not null,
  value bigint not null,
  day_key date not null,
  window_start timestamptz not null,
  window_end timestamptz not null,
  source_payload_json jsonb,
  idempotency_key text not null,
  received_at timestamptz default now(),
  unique (challenge_id, user_wallet, provider, metric, day_key),
  unique (idempotency_key)
);
create index if not exists idx_proofs_challenge_day on proofs(challenge_id, day_key);

create table if not exists payouts (
  id bigserial primary key,
  challenge_id bigint not null references challenges(id),
  user_wallet text not null references users(wallet),
  run_id uuid not null,
  percent_ppm int not null,
  refund_amount numeric(78,0), -- token smallest unit
  charity_amount numeric(78,0),
  commission_amount numeric(78,0),
  reward_from_commission_amount numeric(78,0),
  tx_hash_settlement text,
  settled_at timestamptz,
  unique (challenge_id, user_wallet, run_id)
);

-- Migration-safe: ensure token-agnostic payout amount columns exist
alter table if exists payouts add column if not exists refund_amount numeric(78,0);
alter table if exists payouts add column if not exists charity_amount numeric(78,0);
alter table if exists payouts add column if not exists commission_amount numeric(78,0);
alter table if exists payouts add column if not exists reward_from_commission_amount numeric(78,0);
create index if not exists idx_payouts_challenge on payouts(challenge_id);

create table if not exists integration_tokens (
  wallet text not null,
  provider text not null,
  provider_user_id text,
  scope text,
  access_token_enc text,
  refresh_token_enc text,
  expires_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  primary key(wallet, provider),
  unique (provider, provider_user_id)
);

-- Row Level Security (RLS)
-- Enable RLS on all tables in public schema to satisfy Supabase security best practices.
-- NOTE: The Supabase service_role key used by the backend bypasses RLS; clients using the anon/auth JWT will be restricted by policies below.

alter table if exists users enable row level security;
alter table if exists challenges enable row level security;
alter table if exists stakes enable row level security;
alter table if exists proofs enable row level security;
alter table if exists payouts enable row level security;
alter table if exists integration_tokens enable row level security;

-- Default stance: no policies (deny-all) keeps data private to service_role operations.
-- If you want the frontend to read public/open challenges directly from Supabase with the anon key,
-- you can allow read-only access with the following policy:

do $$ begin
  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'challenges' and policyname = 'Public read open challenges'
  ) then
    create policy "Public read open challenges"
      on public.challenges
      for select
      to anon
      using (status = 'open' and coalesce(is_private, false) = false);
  end if;
end $$;
