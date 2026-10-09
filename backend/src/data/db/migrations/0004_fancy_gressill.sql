CREATE TABLE `edge_captures` (
	`id` bigint unsigned AUTO_INCREMENT NOT NULL,
	`capture_id` varchar(64) NOT NULL,
	`captured_at` datetime(3) NOT NULL,
	`device_id` varchar(128) NOT NULL,
	`model_version` varchar(64) NOT NULL,
	`predicted_class` varchar(150) NOT NULL,
	`confidence` double NOT NULL,
	`latency_ms` double NOT NULL,
	`image_key` varchar(512) NOT NULL,
	`received_at` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `edge_captures_id` PRIMARY KEY(`id`),
	CONSTRAINT `edge_captures_capture_id_unique` UNIQUE(`capture_id`)
);
--> statement-breakpoint
CREATE INDEX `edge_captures_received_at_idx` ON `edge_captures` (`received_at`);--> statement-breakpoint
CREATE INDEX `edge_captures_device_id_idx` ON `edge_captures` (`device_id`);