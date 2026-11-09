CREATE TABLE workspaces (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    plan TEXT NOT NULL CHECK (plan IN ('Team', 'Business'))
);
CREATE TABLE users (
    id             INTEGER PRIMARY KEY,
    workspace_id   INTEGER NOT NULL REFERENCES workspaces(id),
    email          TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('Owner', 'Admin', 'Member', 'Guest')),
    tz             TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    api_token_hash TEXT
);
CREATE TABLE projects (
    id           INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    name         TEXT NOT NULL
);
CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id),
    title       TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('open', 'done')),
    due         TEXT,
    assignee_id INTEGER REFERENCES users(id)
);
CREATE TABLE webhook_deliveries (
    id              INTEGER PRIMARY KEY,
    workspace_id    INTEGER NOT NULL REFERENCES workspaces(id),
    webhook_id      INTEGER NOT NULL,
    attempts        INTEGER NOT NULL CHECK (attempts BETWEEN 1 AND 8),
    status          TEXT NOT NULL CHECK (status IN ('delivered', 'retrying', 'degraded')),
    last_attempt_at TEXT NOT NULL
);

INSERT INTO workspaces VALUES (1, 'Relay Demo Co', 'Business');
INSERT INTO workspaces VALUES (2, 'Kiwi Logistics', 'Team');
INSERT INTO users VALUES (1, 1, 'ana.brandt@example.com', 'Ana Brandt', 'Owner', 'Europe/London', 'pbkdf2$236cdad03da062ed6295ff39c38327d4ba8827b9ba58c5bf', NULL);
INSERT INTO users VALUES (2, 1, 'ben.patel@example.com', 'Ben Patel', 'Admin', 'America/New_York', 'pbkdf2$1a0f49dc2a0f8c9e323cc65265f6bd166c958bbcc511c67f', NULL);
INSERT INTO users VALUES (3, 1, 'cy.ngata@example.com', 'Cy Ngata', 'Member', 'Asia/Kolkata', 'pbkdf2$c9f735a16539c12751b1ae79231544bd6e5e2aef6a5c530e', 'sha256$a2f2b0b588bcc84fbf4d2ac8cc086b6f84de3e00');
INSERT INTO users VALUES (4, 1, 'dee.tanaka@example.com', 'Dee Tanaka', 'Member', 'Europe/Berlin', 'pbkdf2$84eeffb84c46399caf0b30ee04147cadaf85efd7d3a8d3b3', NULL);
INSERT INTO users VALUES (5, 1, 'eru.kowalski@example.com', 'Eru Kowalski', 'Member', 'UTC', 'pbkdf2$9f3992713ec626b7d657ed1e08b5a7ccd52ca6dfe981fad8', NULL);
INSERT INTO users VALUES (6, 1, 'fen.silva@example.com', 'Fen Silva', 'Guest', 'Pacific/Auckland', 'pbkdf2$aec683e8f9e1aa6ec15e5703ea0d8c61064110aeb186cac7', 'sha256$47076dea039ec9db94fc55694f6864a1cfe47d4f');
INSERT INTO users VALUES (7, 2, 'gus.moreau@example.com', 'Gus Moreau', 'Owner', 'Europe/London', 'pbkdf2$88b91feb38b68ba81b97eb538352fc839bb7fedaa9a72ddc', NULL);
INSERT INTO users VALUES (8, 2, 'hana.okafor@example.com', 'Hana Okafor', 'Admin', 'America/New_York', 'pbkdf2$26d4b9d74809add57cac8bf1e4db244d40863b2aef2e5cf3', NULL);
INSERT INTO users VALUES (9, 2, 'ines.brandt@example.com', 'Ines Brandt', 'Member', 'Asia/Kolkata', 'pbkdf2$7ee08482e51d638aedf992bc49e15a8fa3ec92c667c1e6fa', 'sha256$b97607173d82f4f5fc71f828aa26f14cfff17ac6');
INSERT INTO users VALUES (10, 2, 'jo.patel@example.com', 'Jo Patel', 'Member', 'Europe/Berlin', 'pbkdf2$dbfd111b3ac0060a2112c05f55ad8a4f8f9e067cd6694073', NULL);
INSERT INTO users VALUES (11, 2, 'kai.ngata@example.com', 'Kai Ngata', 'Member', 'UTC', 'pbkdf2$6f6490029e6e2f4b0fc3ca114b6a96b60bd3abfb74b27f6d', NULL);
INSERT INTO users VALUES (12, 2, 'lena.tanaka@example.com', 'Lena Tanaka', 'Guest', 'Pacific/Auckland', 'pbkdf2$fcf694b40ba86a2ef3f615c7c415db8c78a9eb721915581c', 'sha256$d6137e5567425e33c104c8b2b0870ed0f67fd271');
INSERT INTO projects VALUES (1, 1, 'Launch');
INSERT INTO projects VALUES (2, 1, 'Platform');
INSERT INTO projects VALUES (3, 2, 'Warehouse app');
INSERT INTO projects VALUES (4, 2, 'Payroll');
INSERT INTO tasks VALUES (1, 1, 'Publish billing report', 'done', NULL, NULL);
INSERT INTO tasks VALUES (2, 1, 'Fix Guest permissions', 'open', '2026-11-08', 3);
INSERT INTO tasks VALUES (3, 1, 'Publish release notes', 'done', '2026-10-21', 2);
INSERT INTO tasks VALUES (4, 1, 'Plan release notes', 'open', '2026-10-27', 4);
INSERT INTO tasks VALUES (5, 1, 'Fix export job', 'done', '2026-12-09', 4);
INSERT INTO tasks VALUES (6, 1, 'Test export job', 'open', '2026-10-25', 6);
INSERT INTO tasks VALUES (7, 1, 'Draft SSO setup guide', 'done', '2026-10-23', 2);
INSERT INTO tasks VALUES (8, 1, 'Fix export job', 'open', '2026-10-13', NULL);
INSERT INTO tasks VALUES (9, 1, 'Fix 100% rollout checklist', 'done', '2026-12-04', NULL);
INSERT INTO tasks VALUES (10, 2, 'Test billing report', 'open', '2026-10-01', 5);
INSERT INTO tasks VALUES (11, 3, 'Review pricing page', 'open', '2026-10-14', 9);
INSERT INTO tasks VALUES (12, 4, 'Fix export job', 'open', '2026-10-31', NULL);
INSERT INTO tasks VALUES (13, 1, 'Review export job', 'done', '2026-10-26', 5);
INSERT INTO tasks VALUES (14, 2, 'Publish pricing page', 'open', '2026-10-18', 4);
INSERT INTO tasks VALUES (15, 3, 'Draft export job', 'open', '2026-11-03', 12);
INSERT INTO tasks VALUES (16, 4, 'Plan export job', 'open', '2026-12-05', 11);
INSERT INTO tasks VALUES (17, 1, 'Document 100% rollout checklist', 'open', '2026-10-06', 2);
INSERT INTO tasks VALUES (18, 2, 'Test 100% rollout checklist', 'open', '2026-10-17', 5);
INSERT INTO tasks VALUES (19, 3, 'Test onboarding email', 'open', '2026-11-27', 7);
INSERT INTO tasks VALUES (20, 4, 'Publish SSO setup guide', 'open', '2026-10-23', 10);
INSERT INTO tasks VALUES (21, 1, 'Draft Guest permissions', 'open', '2026-11-22', 5);
INSERT INTO tasks VALUES (22, 2, 'Draft 100% rollout checklist', 'open', NULL, 6);
INSERT INTO tasks VALUES (23, 3, 'Plan webhook retries', 'done', '2026-11-17', 7);
INSERT INTO tasks VALUES (24, 4, 'Test webhook retries', 'open', '2026-11-05', 7);
INSERT INTO tasks VALUES (25, 1, 'Draft onboarding email', 'done', '2026-11-10', NULL);
INSERT INTO tasks VALUES (26, 2, 'Test pricing page', 'open', '2026-11-02', 5);
INSERT INTO tasks VALUES (27, 3, 'Migrate export job', 'done', '2026-10-02', 11);
INSERT INTO tasks VALUES (28, 4, 'Fix SSO setup guide', 'done', '2026-12-02', 12);
INSERT INTO tasks VALUES (29, 1, 'Migrate pricing page', 'open', '2026-12-09', 6);
INSERT INTO tasks VALUES (30, 2, 'Migrate pricing page', 'open', '2026-11-27', 5);
INSERT INTO tasks VALUES (31, 3, 'Migrate billing report', 'done', '2026-10-13', NULL);
INSERT INTO tasks VALUES (32, 4, 'Review 100% rollout checklist', 'open', NULL, 12);
INSERT INTO tasks VALUES (33, 1, 'Migrate Guest permissions', 'open', '2026-10-11', 4);
INSERT INTO tasks VALUES (34, 2, 'Fix 100% rollout checklist', 'open', NULL, NULL);
INSERT INTO tasks VALUES (35, 3, 'Test pricing page', 'open', '2026-10-03', 12);
INSERT INTO tasks VALUES (36, 4, 'Plan 100% rollout checklist', 'done', '2026-11-26', 10);
INSERT INTO tasks VALUES (37, 1, 'Review onboarding email', 'done', '2026-10-22', 1);
INSERT INTO tasks VALUES (38, 2, 'Document release notes', 'open', '2026-11-18', 2);
INSERT INTO tasks VALUES (39, 3, 'Migrate onboarding email', 'open', '2026-12-10', 12);
INSERT INTO tasks VALUES (40, 4, 'Plan webhook retries', 'open', '2026-12-06', 7);
INSERT INTO tasks VALUES (41, 1, 'Plan onboarding email', 'done', '2026-11-28', 4);
INSERT INTO tasks VALUES (42, 2, 'Plan 100% rollout checklist', 'open', '2026-11-01', 6);
INSERT INTO tasks VALUES (43, 3, 'Review webhook retries', 'open', '2026-11-15', 12);
INSERT INTO tasks VALUES (44, 4, 'Plan SSO setup guide', 'open', '2026-12-13', 9);
INSERT INTO tasks VALUES (45, 1, 'Fix Guest permissions', 'open', '2026-12-05', NULL);
INSERT INTO tasks VALUES (46, 2, 'Draft pricing page', 'open', '2026-11-27', 5);
INSERT INTO tasks VALUES (47, 3, 'Plan webhook retries', 'open', NULL, 9);
INSERT INTO tasks VALUES (48, 4, 'Migrate webhook retries', 'open', '2026-10-02', 12);
INSERT INTO tasks VALUES (49, 1, 'Migrate webhook retries', 'open', '2026-11-20', 1);
INSERT INTO tasks VALUES (50, 2, 'Plan release notes', 'open', '2026-10-19', 3);
INSERT INTO tasks VALUES (51, 3, 'Document SSO setup guide', 'open', '2026-10-29', 9);
INSERT INTO tasks VALUES (52, 4, 'Test SSO setup guide', 'open', '2026-11-05', 11);
INSERT INTO tasks VALUES (53, 1, 'Draft onboarding email', 'open', '2026-11-27', 5);
INSERT INTO tasks VALUES (54, 2, 'Plan webhook retries', 'open', '2026-11-08', 2);
INSERT INTO tasks VALUES (55, 3, 'Publish export job', 'open', '2026-11-22', 9);
INSERT INTO tasks VALUES (56, 4, 'Test webhook retries', 'open', '2026-10-07', 7);
INSERT INTO tasks VALUES (57, 1, 'Test pricing page', 'done', '2026-10-27', 2);
INSERT INTO tasks VALUES (58, 2, 'Migrate export job', 'open', '2026-11-21', 2);
INSERT INTO tasks VALUES (59, 3, 'Test billing report', 'done', '2026-10-23', 7);
INSERT INTO tasks VALUES (60, 4, 'Review onboarding email', 'done', '2026-11-10', 8);
INSERT INTO tasks VALUES (61, 1, 'Fix webhook retries', 'open', '2026-11-06', 1);
INSERT INTO tasks VALUES (62, 2, 'Document onboarding email', 'open', '2026-11-01', 1);
INSERT INTO tasks VALUES (63, 3, 'Publish billing report', 'open', '2026-10-03', 12);
INSERT INTO tasks VALUES (64, 4, 'Draft Guest permissions', 'open', '2026-10-19', 12);
INSERT INTO tasks VALUES (65, 1, 'Review 100% rollout checklist', 'open', '2026-11-19', NULL);
INSERT INTO tasks VALUES (66, 2, 'Document webhook retries', 'open', '2026-10-09', 4);
INSERT INTO tasks VALUES (67, 3, 'Publish Guest permissions', 'done', '2026-10-16', 8);
INSERT INTO tasks VALUES (68, 4, 'Review billing report', 'open', '2026-11-18', 11);
INSERT INTO tasks VALUES (69, 1, 'Test 100% rollout checklist', 'open', '2026-11-11', 5);
INSERT INTO tasks VALUES (70, 2, 'Review webhook retries', 'done', '2026-10-23', 6);
INSERT INTO tasks VALUES (71, 3, 'Review billing report', 'open', '2026-11-10', 10);
INSERT INTO tasks VALUES (72, 4, 'Review onboarding email', 'open', '2026-12-14', 9);
INSERT INTO tasks VALUES (73, 1, 'Fix billing report', 'done', '2026-10-31', 5);
INSERT INTO tasks VALUES (74, 2, 'Fix SSO setup guide', 'done', '2026-11-11', NULL);
INSERT INTO tasks VALUES (75, 3, 'Document SSO setup guide', 'done', '2026-11-07', 10);
INSERT INTO tasks VALUES (76, 4, 'Publish webhook retries', 'open', '2026-10-25', 7);
INSERT INTO tasks VALUES (77, 1, 'Review export job', 'done', '2026-10-30', 1);
INSERT INTO tasks VALUES (78, 2, 'Migrate webhook retries', 'open', '2026-11-16', 1);
INSERT INTO tasks VALUES (79, 3, 'Review export job', 'open', NULL, 9);
INSERT INTO tasks VALUES (80, 4, 'Document release notes', 'open', NULL, 8);
INSERT INTO webhook_deliveries VALUES (1, 2, 101, 1, 'delivered', '2026-11-02T10:17:00Z');
INSERT INTO webhook_deliveries VALUES (2, 1, 102, 5, 'delivered', '2026-11-03T06:15:00Z');
INSERT INTO webhook_deliveries VALUES (3, 2, 103, 1, 'delivered', '2026-11-04T20:27:00Z');
INSERT INTO webhook_deliveries VALUES (4, 1, 104, 3, 'delivered', '2026-11-05T15:46:00Z');
INSERT INTO webhook_deliveries VALUES (5, 2, 100, 1, 'delivered', '2026-11-06T06:22:00Z');
INSERT INTO webhook_deliveries VALUES (6, 1, 101, 1, 'delivered', '2026-11-07T04:01:00Z');
INSERT INTO webhook_deliveries VALUES (7, 2, 102, 5, 'retrying', '2026-11-01T10:22:00Z');
INSERT INTO webhook_deliveries VALUES (8, 1, 103, 5, 'retrying', '2026-11-02T13:32:00Z');
INSERT INTO webhook_deliveries VALUES (9, 2, 104, 1, 'delivered', '2026-11-03T07:32:00Z');
INSERT INTO webhook_deliveries VALUES (10, 1, 100, 3, 'retrying', '2026-11-04T05:36:00Z');
INSERT INTO webhook_deliveries VALUES (11, 2, 101, 5, 'delivered', '2026-11-05T02:52:00Z');
INSERT INTO webhook_deliveries VALUES (12, 1, 102, 8, 'degraded', '2026-11-06T01:25:00Z');
INSERT INTO webhook_deliveries VALUES (13, 2, 103, 1, 'delivered', '2026-11-07T07:19:00Z');
INSERT INTO webhook_deliveries VALUES (14, 1, 104, 3, 'retrying', '2026-11-01T03:50:00Z');
INSERT INTO webhook_deliveries VALUES (15, 2, 100, 2, 'delivered', '2026-11-02T18:45:00Z');
INSERT INTO webhook_deliveries VALUES (16, 1, 101, 2, 'retrying', '2026-11-03T02:56:00Z');
INSERT INTO webhook_deliveries VALUES (17, 2, 102, 1, 'delivered', '2026-11-04T22:32:00Z');
INSERT INTO webhook_deliveries VALUES (18, 1, 103, 2, 'delivered', '2026-11-05T16:24:00Z');
INSERT INTO webhook_deliveries VALUES (19, 2, 104, 8, 'degraded', '2026-11-06T01:24:00Z');
INSERT INTO webhook_deliveries VALUES (20, 1, 100, 1, 'delivered', '2026-11-07T14:34:00Z');
INSERT INTO webhook_deliveries VALUES (21, 2, 101, 2, 'delivered', '2026-11-01T06:56:00Z');
INSERT INTO webhook_deliveries VALUES (22, 1, 102, 1, 'delivered', '2026-11-02T13:14:00Z');
INSERT INTO webhook_deliveries VALUES (23, 2, 103, 8, 'degraded', '2026-11-03T01:23:00Z');
INSERT INTO webhook_deliveries VALUES (24, 1, 104, 1, 'delivered', '2026-11-04T14:10:00Z');
INSERT INTO webhook_deliveries VALUES (25, 2, 100, 5, 'retrying', '2026-11-05T23:28:00Z');
INSERT INTO webhook_deliveries VALUES (26, 1, 101, 2, 'retrying', '2026-11-06T21:21:00Z');
INSERT INTO webhook_deliveries VALUES (27, 2, 102, 1, 'delivered', '2026-11-07T10:30:00Z');
INSERT INTO webhook_deliveries VALUES (28, 1, 103, 1, 'delivered', '2026-11-01T15:38:00Z');
INSERT INTO webhook_deliveries VALUES (29, 2, 104, 5, 'delivered', '2026-11-02T12:35:00Z');
INSERT INTO webhook_deliveries VALUES (30, 1, 100, 2, 'retrying', '2026-11-03T19:41:00Z');
