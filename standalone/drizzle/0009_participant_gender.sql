-- Gender (female, male or na) is asked beside the nickname and is required for new sessions from 2026-09-15.
-- Sessions saved before then keep NULL; withdrawal clears the value together with the nickname.
ALTER TABLE `study_sessions` ADD `gender` text;--> statement-breakpoint
ALTER TABLE `interactive_sessions` ADD `gender` text;
