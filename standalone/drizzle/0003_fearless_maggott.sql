-- Preserve parent and child records while extending the approved engine set. Foreign keys remain ON.
-- Build the new child against the new parent before dropping either original table.
CREATE TABLE `__new_interactive_sessions` (
	`session_id` text PRIMARY KEY NOT NULL,
	`token_hash` text NOT NULL,
	`nickname` text NOT NULL,
	`mode` text NOT NULL,
	`engine` text,
	`record_type` text NOT NULL,
	`version` text NOT NULL,
	`consent_utc` text NOT NULL,
	`received_utc` text NOT NULL,
	`updated_utc` text NOT NULL,
	`withdrawn_utc` text,
	CONSTRAINT "interactive_mode" CHECK("__new_interactive_sessions"."mode" IN ('line','explore')),
	CONSTRAINT "interactive_engine" CHECK("__new_interactive_sessions"."engine" IS NULL OR "__new_interactive_sessions"."engine" IN ('pyttsx3','sapi5xml','espeak','kokoro','chatterbox','zipvoice','styletts2','cosyvoice2','parlertts','piper')),
	CONSTRAINT "interactive_type" CHECK("__new_interactive_sessions"."record_type" IN ('interactive_exploration','technical_test')),
	CONSTRAINT "interactive_engine_mode" CHECK(("__new_interactive_sessions"."mode"='explore' AND "__new_interactive_sessions"."engine" IS NOT NULL) OR ("__new_interactive_sessions"."mode"='line' AND "__new_interactive_sessions"."engine" IS NULL))
);
--> statement-breakpoint
INSERT INTO `__new_interactive_sessions`("session_id", "token_hash", "nickname", "mode", "engine", "record_type", "version", "consent_utc", "received_utc", "updated_utc", "withdrawn_utc") SELECT "session_id", "token_hash", "nickname", "mode", "engine", "record_type", "version", "consent_utc", "received_utc", "updated_utc", "withdrawn_utc" FROM `interactive_sessions`;
--> statement-breakpoint
CREATE TABLE `__new_interactive_turns` (
	`session_id` text NOT NULL,
	`turn_order` integer NOT NULL,
	`engine` text NOT NULL,
	`emotion` text NOT NULL,
	`input_text` text NOT NULL,
	`output_text` text NOT NULL,
	`turn_json` text NOT NULL,
	`created_utc` text NOT NULL,
	`received_utc` text NOT NULL,
	PRIMARY KEY(`session_id`, `turn_order`),
	FOREIGN KEY (`session_id`) REFERENCES `__new_interactive_sessions`(`session_id`) ON UPDATE no action ON DELETE cascade,
	CONSTRAINT "interactive_order" CHECK("__new_interactive_turns"."turn_order" BETWEEN 1 AND 100),
	CONSTRAINT "interactive_turn_engine" CHECK("__new_interactive_turns"."engine" IN ('pyttsx3','sapi5xml','espeak','kokoro','chatterbox','zipvoice','styletts2','cosyvoice2','parlertts','piper')),
	CONSTRAINT "interactive_emotion" CHECK("__new_interactive_turns"."emotion" IN ('happy','upset','sad','calm'))
);
--> statement-breakpoint
INSERT INTO `__new_interactive_turns`("session_id", "turn_order", "engine", "emotion", "input_text", "output_text", "turn_json", "created_utc", "received_utc") SELECT "session_id", "turn_order", "engine", "emotion", "input_text", "output_text", "turn_json", "created_utc", "received_utc" FROM `interactive_turns`;
--> statement-breakpoint
DROP TABLE `interactive_turns`;
--> statement-breakpoint
DROP TABLE `interactive_sessions`;
--> statement-breakpoint
ALTER TABLE `__new_interactive_sessions` RENAME TO `interactive_sessions`;
--> statement-breakpoint
ALTER TABLE `__new_interactive_turns` RENAME TO `interactive_turns`;
--> statement-breakpoint
CREATE INDEX `idx_interactive_sessions_updated` ON `interactive_sessions` (`updated_utc`);
