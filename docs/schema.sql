
create table if not exists public.chain_challenges (
	contract_address text not null,
	challenge_id bigint not null,
	recipient text not null,
	start_time bigint not null,
	end_time bigint not null,
	is_private boolean not null,
	name text not null,
	api_type text not null,
	goal_type text not null,
	goal_amount numeric(78,0) not null,
	description text not null,
	total_donation_amount numeric(78,0) not null,
	results_finalized boolean not null,
	participant_count bigint not null,
	indexed_at timestamptz default now() not null,
	primary key (contract_address, challenge_id)
);

create index if not exists idx_chain_challenges_end_ready on public.chain_challenges (end_time, results_finalized);

create table if not exists public.chain_participants (
	contract_address text not null,
	challenge_id bigint not null,
	participant_address text not null,
	amount numeric(78,0) not null,
	refund_percentage numeric(78,0) not null,
	result_declared boolean not null,
	indexed_at timestamptz default now() not null,
	primary key (contract_address, challenge_id, participant_address)
);

create index if not exists idx_chain_participants_challenge on public.chain_participants (contract_address, challenge_id);

-- Finished challenges archive for processed items
create table if not exists public.finished_challenges (
    contract_address text not null,
    challenge_id bigint not null,
    processed_at timestamptz default now(),
    rule jsonb, -- computation rule/details used for declareResults
    summary jsonb, -- optional summary/receipt
    primary key (contract_address, challenge_id)
);

-- Per-participant archived results for processed challenges
create table if not exists public.finished_participants (
	contract_address text not null,
	challenge_id bigint not null,
	participant_address text not null,
	stake_minor_units numeric(78,0) not null,
	percent_ppm bigint not null,
	progress_ratio numeric, -- optional: if you choose to store ratios (0..1)
	batch_no int,           -- optional: chunk index if submitted in batches
	tx_hash text,           -- optional: on-chain tx hash for this batch/item
	archived_at timestamptz default now() not null,
	primary key (contract_address, challenge_id, participant_address)
);
create index if not exists idx_finished_participants_chal on public.finished_participants (contract_address, challenge_id);
create index if not exists idx_finished_participants_user on public.finished_participants (lower(participant_address));

-- Per-wallet provider tokens used for progress fetching (optional)
-- Store wallet_address lowercased to match code lookups.
create table if not exists public.user_tokens (
	wallet_address text not null,
	provider text not null,
	access_token text not null,
	refresh_token text,
	expires_at timestamptz,
	scopes text[],
	created_at timestamptz default now() not null,
	updated_at timestamptz default now() not null,
	primary key (wallet_address, provider)
);
create index if not exists idx_user_tokens_wallet_lower on public.user_tokens (lower(wallet_address));
