ALTER TABLE `edge_captures` ADD `crop_x` double;--> statement-breakpoint
ALTER TABLE `edge_captures` ADD `crop_y` double;--> statement-breakpoint
ALTER TABLE `edge_captures` ADD `crop_width` double;--> statement-breakpoint
ALTER TABLE `edge_captures` ADD `crop_height` double;--> statement-breakpoint
CREATE INDEX `edge_captures_captured_at_id_idx` ON `edge_captures` (`captured_at`,`id`);