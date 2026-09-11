-- Rebuild the child response table with foreign keys enforced; no table references it.
CREATE TABLE `__new_study_responses` (
	`participant_id` text NOT NULL,
	`trial_order` integer NOT NULL,
	`item_id` text NOT NULL,
	`block_id` text NOT NULL,
	`valence` real NOT NULL,
	`arousal` real NOT NULL,
	`naturalness` integer NOT NULL,
	`target_match` real,
	`play_count` integer NOT NULL,
	`completed_audio` integer NOT NULL,
	`elapsed_s` real NOT NULL,
	`created_utc` text NOT NULL,
	`received_utc` text NOT NULL,
	`completed_utc` text,
	PRIMARY KEY(`participant_id`, `trial_order`),
	FOREIGN KEY (`participant_id`) REFERENCES `study_sessions`(`participant_id`) ON UPDATE no action ON DELETE cascade,
	CONSTRAINT "response_order" CHECK("__new_study_responses"."trial_order" BETWEEN 1 AND 45),
	CONSTRAINT "response_valence" CHECK("__new_study_responses"."valence" BETWEEN -1 AND 1),
	CONSTRAINT "response_arousal" CHECK("__new_study_responses"."arousal" BETWEEN -1 AND 1),
	CONSTRAINT "response_naturalness" CHECK("__new_study_responses"."naturalness" BETWEEN 1 AND 5),
	CONSTRAINT "response_target_match" CHECK("__new_study_responses"."target_match" IS NULL OR "__new_study_responses"."target_match" BETWEEN 1 AND 5)
);
--> statement-breakpoint
INSERT INTO `__new_study_responses`("participant_id", "trial_order", "item_id", "block_id", "valence", "arousal", "naturalness", "target_match", "play_count", "completed_audio", "elapsed_s", "created_utc", "received_utc", "completed_utc") SELECT "participant_id", "trial_order", "item_id", "block_id", "valence", "arousal", "naturalness", "target_match", "play_count", "completed_audio", "elapsed_s", "created_utc", "received_utc", "completed_utc" FROM `study_responses`;--> statement-breakpoint
DROP TABLE `study_responses`;--> statement-breakpoint
ALTER TABLE `__new_study_responses` RENAME TO `study_responses`;--> statement-breakpoint
CREATE UNIQUE INDEX `idx_response_session_item` ON `study_responses` (`participant_id`,`item_id`);
