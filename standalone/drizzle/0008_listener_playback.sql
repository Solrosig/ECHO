-- A random listener code links one browser's Listening, Test and Explore sessions; playback events record listening
-- behaviour, including when an Explore transcript is opened or closed.
ALTER TABLE `study_sessions` ADD `listener_id` text;--> statement-breakpoint
ALTER TABLE `interactive_sessions` ADD `listener_id` text;--> statement-breakpoint
CREATE INDEX `idx_study_sessions_listener` ON `study_sessions` (`listener_id`);--> statement-breakpoint
CREATE INDEX `idx_interactive_sessions_listener` ON `interactive_sessions` (`listener_id`);--> statement-breakpoint
CREATE TABLE `playback_events` (
	`session_kind` text NOT NULL,
	`session_id` text NOT NULL,
	`event_id` text NOT NULL,
	`seq` integer NOT NULL,
	`event` text NOT NULL,
	`item_order` integer NOT NULL,
	`item_id` text,
	`position_s` real NOT NULL,
	`duration_s` real,
	`playback_rate` real NOT NULL,
	`autoplay` integer NOT NULL,
	`client_utc` text NOT NULL,
	`received_utc` text NOT NULL,
	PRIMARY KEY(`session_kind`, `session_id`, `event_id`),
	CONSTRAINT "playback_kind" CHECK("playback_events"."session_kind" IN ('study', 'interactive')),
	CONSTRAINT "playback_event" CHECK("playback_events"."event" IN ('play', 'pause', 'ended', 'seeked', 'transcript_open', 'transcript_close'))
);--> statement-breakpoint
CREATE INDEX `idx_playback_session_seq` ON `playback_events` (`session_kind`,`session_id`,`seq`);
