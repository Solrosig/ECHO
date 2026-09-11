CREATE TABLE `interactive_audio` (
	`session_id` text NOT NULL,
	`turn_order` integer NOT NULL,
	`sha256` text NOT NULL,
	`object_key` text NOT NULL,
	`byte_length` integer NOT NULL,
	`sample_rate` integer NOT NULL,
	`duration_s` real NOT NULL,
	`stored_utc` text NOT NULL,
	PRIMARY KEY(`session_id`, `turn_order`),
	FOREIGN KEY (`session_id`,`turn_order`) REFERENCES `interactive_turns`(`session_id`,`turn_order`) ON UPDATE no action ON DELETE cascade
);
