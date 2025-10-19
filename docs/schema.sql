-- Essential tables and indices for Motify (Supabase/Postgres)

-- Minimal chain challenges index (append this to your Supabase project)
create table if not exists public.chain_challenges (
	contract_address text not null,
	challenge_id bigint not null,
	recipient text not null,
	start_time bigint not null,
	end_time bigint not null,
	is_private boolean not null,
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

-- Chain participants detail cache
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

--
-- Row Level Security (RLS) and policies
-- These settings ensure only the service role can write, while anon/authenticated can optionally read.
-- The service_role bypasses RLS automatically. Do not add insert/update/delete policies for anon/auth.

-- Enable RLS and revoke broad grants
alter table public.chain_challenges enable row level security;
revoke all on table public.chain_challenges from anon, authenticated;

alter table public.chain_participants enable row level security;
revoke all on table public.chain_participants from anon, authenticated;

-- Optional: Public read-only access (anon + authenticated) to cache tables
-- If you do not want public reads, comment these out.
create policy if not exists "read_chain_challenges"
on public.chain_challenges for select
to anon, authenticated
using (true);

create policy if not exists "read_chain_participants"
on public.chain_participants for select
to anon, authenticated
using (true);
