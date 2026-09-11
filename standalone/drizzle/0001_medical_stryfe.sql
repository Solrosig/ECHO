CREATE TABLE `interactive_sessions` (
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
	CONSTRAINT "interactive_mode" CHECK("interactive_sessions"."mode" IN ('line','explore')),
	CONSTRAINT "interactive_engine" CHECK("interactive_sessions"."engine" IS NULL OR "interactive_sessions"."engine" IN ('espeak','kokoro','piper')),
	CONSTRAINT "interactive_type" CHECK("interactive_sessions"."record_type" IN ('interactive_exploration','technical_test')),
	CONSTRAINT "interactive_engine_mode" CHECK(("interactive_sessions"."mode"='explore' AND "interactive_sessions"."engine" IS NOT NULL) OR ("interactive_sessions"."mode"='line' AND "interactive_sessions"."engine" IS NULL))
);
--> statement-breakpoint
CREATE INDEX `idx_interactive_sessions_updated` ON `interactive_sessions` (`updated_utc`);--> statement-breakpoint
CREATE TABLE `interactive_turns` (
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
	FOREIGN KEY (`session_id`) REFERENCES `interactive_sessions`(`session_id`) ON UPDATE no action ON DELETE cascade,
	CONSTRAINT "interactive_order" CHECK("interactive_turns"."turn_order" BETWEEN 1 AND 100),
	CONSTRAINT "interactive_turn_engine" CHECK("interactive_turns"."engine" IN ('espeak','kokoro','piper')),
	CONSTRAINT "interactive_emotion" CHECK("interactive_turns"."emotion" IN ('happy','upset','sad','calm'))
);
--> statement-breakpoint
ALTER TABLE `study_sessions` ADD `nickname` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `study_sessions` ADD `rating_scale` text DEFAULT 'va-0.05_match-1_naturalness-1_v1' NOT NULL;