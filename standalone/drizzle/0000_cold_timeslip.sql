CREATE TABLE `study_responses` (
	`participant_id` text NOT NULL,
	`trial_order` integer NOT NULL,
	`item_id` text NOT NULL,
	`block_id` text NOT NULL,
	`valence` real NOT NULL,
	`arousal` real NOT NULL,
	`naturalness` integer NOT NULL,
	`target_match` integer,
	`play_count` integer NOT NULL,
	`completed_audio` integer NOT NULL,
	`elapsed_s` real NOT NULL,
	`created_utc` text NOT NULL,
	`received_utc` text NOT NULL,
	`completed_utc` text,
	PRIMARY KEY(`participant_id`, `trial_order`),
	FOREIGN KEY (`participant_id`) REFERENCES `study_sessions`(`participant_id`) ON UPDATE no action ON DELETE cascade,
	CONSTRAINT "response_order" CHECK("study_responses"."trial_order" BETWEEN 1 AND 26),
	CONSTRAINT "response_valence" CHECK("study_responses"."valence" BETWEEN -1 AND 1),
	CONSTRAINT "response_arousal" CHECK("study_responses"."arousal" BETWEEN -1 AND 1),
	CONSTRAINT "response_naturalness" CHECK("study_responses"."naturalness" BETWEEN 1 AND 5),
	CONSTRAINT "response_target_match" CHECK("study_responses"."target_match" IS NULL OR "study_responses"."target_match" BETWEEN 1 AND 5)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_response_session_item` ON `study_responses` (`participant_id`,`item_id`);--> statement-breakpoint
CREATE TABLE `study_sessions` (
	`participant_id` text PRIMARY KEY NOT NULL,
	`token_hash` text NOT NULL,
	`study_version` text NOT NULL,
	`collection_version` text NOT NULL,
	`record_type` text NOT NULL,
	`group_number` integer NOT NULL,
	`seed` integer NOT NULL,
	`comfortable_english` integer NOT NULL,
	`headphones` integer NOT NULL,
	`previously_used_studio` integer NOT NULL,
	`consent_utc` text NOT NULL,
	`received_utc` text NOT NULL,
	`updated_utc` text NOT NULL,
	`completed_utc` text,
	`withdrawn_utc` text,
	CONSTRAINT "session_type" CHECK("study_sessions"."record_type" IN ('human_response', 'technical_test')),
	CONSTRAINT "session_group" CHECK("study_sessions"."group_number" BETWEEN 1 AND 16),
	CONSTRAINT "session_seed" CHECK("study_sessions"."seed" BETWEEN 0 AND 4294967295)
);
--> statement-breakpoint
CREATE INDEX `idx_sessions_type_group` ON `study_sessions` (`record_type`,`group_number`);