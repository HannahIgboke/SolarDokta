-- 010_whatsapp.sql
-- WhatsApp: Igbo as a saved language, and quick lookups for chats and alerts.

alter table public.profiles drop constraint if exists profiles_preferred_language_check;
alter table public.profiles add constraint profiles_preferred_language_check
  check (preferred_language in ('en', 'pcm', 'ig'));

create index if not exists alerts_created_idx on public.alerts (created_at desc);
create index if not exists alerts_provider_idx on public.alerts (provider_message_id);
create index if not exists findings_created_idx on public.findings (created_at desc);
create index if not exists conversations_created_idx on public.conversations (created_at);
