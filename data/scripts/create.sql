CREATE TABLE IF NOT EXISTS challenges (
    id integer PRIMARY KEY,
    created text not null,
    guild_id bigint not null,
    text_channel_id bigint not null,
    message_id bigint not null unique,
    challenge_type text not null,
    responding_member_id bigint null default NULL,
    responded_at text null default NULL

);
create index if not exists idx_challenge_guild_id on challenges(guild_id);
--create index if not exists idx_challenge_responding_member_id on challenges(responding_member_id);

create table if not exists match_type_roles (
    id integer primary key,
    guild_id bigint not null,
    match_type text not null,
    role_id bigint not null,
    unique (guild_id, match_type, role_id)

);
create index if not exists idx_match_type_roles_guild_id_and_match_type on match_type_roles(guild_id, match_type);


