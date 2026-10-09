-- archive_note: when and why a note was taken out of search.
ALTER TABLE notes ADD COLUMN archived_at timestamptz;
ALTER TABLE notes ADD COLUMN archived_reason text;
