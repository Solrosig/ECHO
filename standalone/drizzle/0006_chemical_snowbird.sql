CREATE TABLE `generation_attempts` (
	`session_id` text NOT NULL,
	`attempt_id` text NOT NULL,
	`event_json` text NOT NULL,
	`received_utc` text NOT NULL,
	PRIMARY KEY(`session_id`, `attempt_id`),
	FOREIGN KEY (`session_id`) REFERENCES `interactive_sessions`(`session_id`) ON UPDATE no action ON DELETE cascade
);
