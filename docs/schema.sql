-- Essential tables and indices for Motify (Supabase/Postgres)

create table if not exists users (
  wallet text primary key,
  created_at timestamptz default now()
);

create table if not exists challenges (
  id bigserial primary key,
  owner_wallet text,
  title text not null,
  start_at timestamptz not null,
  end_at timestamptz not null,
  target_metric text not null,
  target_value bigint not null,
  charity_wallet text,
  is_private boolean default false,
  invite_code text,
  allowed_wallets text[],
  stake_token text,
  proof_policy jsonb,
  status text default 'open'
);
create index if not exists idx_challenges_owner on challenges(owner_wallet);

create table if not exists stakes (
  id bigserial primary key,
  challenge_id bigint not null references challenges(id),
  user_wallet text not null references users(wallet),
  amount_wei numeric(78,0) not null,
  token_address text,
  decimals int,
  tx_hash_deposit text,
  joined_via text,
  unique (challenge_id, user_wallet)
);

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
  refund_amount_wei numeric(78,0),
  charity_amount_wei numeric(78,0),
  commission_wei numeric(78,0),
  reward_from_commission_wei numeric(78,0),
  tx_hash_settlement text,
  settled_at timestamptz,
  unique (challenge_id, user_wallet, run_id)
);
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
