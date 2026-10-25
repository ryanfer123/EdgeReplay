-- Additive migration: creates only this application's private snapshot table.
begin;
create table public.edge_replay_cloud_workspaces (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    title text not null check (char_length(btrim(title)) between 1 and 120),
    payload jsonb not null check (jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 8388608),
    created_at timestamptz not null default now()
);
create index edge_replay_cloud_workspaces_owner_created_idx
    on public.edge_replay_cloud_workspaces (owner_id, created_at desc);
alter table public.edge_replay_cloud_workspaces enable row level security;
revoke all on public.edge_replay_cloud_workspaces from anon;
grant select, insert, update, delete on public.edge_replay_cloud_workspaces to authenticated;
create policy "Read own workspaces" on public.edge_replay_cloud_workspaces
    for select to authenticated using ((select auth.uid()) = owner_id);
create policy "Create own workspaces" on public.edge_replay_cloud_workspaces
    for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy "Update own workspaces" on public.edge_replay_cloud_workspaces
    for update to authenticated using ((select auth.uid()) = owner_id)
    with check ((select auth.uid()) = owner_id);
create policy "Delete own workspaces" on public.edge_replay_cloud_workspaces
    for delete to authenticated using ((select auth.uid()) = owner_id);
commit;
