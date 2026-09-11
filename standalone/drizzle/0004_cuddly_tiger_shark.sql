CREATE TABLE `interactive_ratings` (
	`session_id` text NOT NULL,
	`turn_order` integer NOT NULL,
	`valence` real NOT NULL,
	`arousal` real NOT NULL,
	`naturalness` integer NOT NULL,
	`target_match` real NOT NULL,
	`rating_scale` text NOT NULL,
	`rating_json` text NOT NULL,
	`created_utc` text NOT NULL,
	`received_utc` text NOT NULL,
	PRIMARY KEY(`session_id`, `turn_order`),
	FOREIGN KEY (`session_id`,`turn_order`) REFERENCES `interactive_turns`(`session_id`,`turn_order`) ON UPDATE no action ON DELETE cascade,
	CONSTRAINT "message_valence" CHECK("interactive_ratings"."valence" BETWEEN -1 AND 1),
	CONSTRAINT "message_arousal" CHECK("interactive_ratings"."arousal" BETWEEN -1 AND 1),
	CONSTRAINT "message_naturalness" CHECK("interactive_ratings"."naturalness" BETWEEN 1 AND 5),
	CONSTRAINT "message_match" CHECK("interactive_ratings"."target_match" BETWEEN 1 AND 5)
);
