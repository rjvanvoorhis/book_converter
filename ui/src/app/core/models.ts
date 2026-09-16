export interface VoiceProfile {
  id: string;
  description: string | null;
}

export interface FileBrowserEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface FileBrowserListing {
  path: string;
  parent: string | null;
  entries: FileBrowserEntry[];
}

export interface CreateAudiobookRequest {
  identifier: string;
  name: string;
  audiobook_folder: string;
  source: string;
  tts_provider: string;
  engine: string;
  voice: string;
  pronunciations?: string | null;
  add_pauses?: boolean;
  batch_size?: number;
  chapters_per_chunk?: number | null;
  dialogue_voice?: string | null;
}

export interface CreateSampleRequest {
  identifier: string;
  source: string;
  tts_provider: string;
  engine: string;
  voice: string;
  sentence_count?: number;
  pronunciations?: string | null;
  add_pauses?: boolean;
}

export interface CreateAudiobookResult {
  destinations: string[];
  transcripts: string[];
  total_duration: number;
}

export interface CreateAudiobookTask {
  task_id: string;
}

export type AudiobookTaskStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface AudiobookTaskState<TResult = CreateAudiobookResult> {
  id: string;
  status: AudiobookTaskStatus;
  message: string;
  result: TResult | null;
  error: string | null;
}

export interface AudiobookSummary {
  path: string;
  title: string;
  segment_count: number;
}

export interface TranscriptSegment {
  chapter_title: string;
  speaker: string | null;
  text: string;
  start_seconds: number;
  end_seconds: number;
}

export interface Transcript {
  audiobook: string;
  title: string;
  segments: TranscriptSegment[];
}

export interface ArtifactCut {
  start_seconds: number;
  end_seconds: number;
}

export type ReviewStatus = 'ok' | 'flagged' | 'fixed';

export interface ReviewEntry {
  status: ReviewStatus;
  note?: string;
}

export interface ReviewState {
  segments: Record<string, ReviewEntry>;
}

export interface DetectArtifactsResult {
  cuts: ArtifactCut[];
}

export interface ResegmentTranscriptResult {
  original_segment_count: number;
  new_segment_count: number;
  segments_split: number;
}

// Staged edits live on disk (see pending_edit_store) until applied - a
// "regenerate" edit's audio is the actual take (not a disposable preview),
// already synthesized and ready to listen to; a "cut" edit is just the
// [start, end) range to drop, applied directly against the existing audio.
export interface PendingRegenerateEdit {
  kind: 'regenerate';
  text: string;
  duration: number;
}

export interface PendingCutEdit {
  kind: 'cut';
  cut_start_seconds: number;
  cut_end_seconds: number;
}

export type PendingEdit = PendingRegenerateEdit | PendingCutEdit;

export type PendingEdits = Record<string, PendingEdit>;

export interface StageRegenerationRequest {
  path: string;
  segment_index: number;
  text: string;
  tts_provider: string;
  engine: string;
  voice: string;
  dialogue_voice?: string | null;
  pronunciations?: string | null;
  add_pauses?: boolean;
}

export interface StageRegenerationResult {
  segment_index: number;
  edits: PendingEdits;
}

export interface StageCutRequest {
  path: string;
  segment_index: number;
  cut_start_seconds: number;
  cut_end_seconds: number;
}

export interface ApplyEditsResult {
  destination: string;
  segments_applied: number;
}

export type PronunciationMethod = 'ipa' | 'spelling';

export interface PronunciationDictSummary {
  path: string;
  name: string;
}

export interface PronunciationEntry {
  value: string;
  method: PronunciationMethod;
}

export interface VoiceSampleSummary {
  path: string;
  name: string;
  duration_seconds: number;
}

export interface VoiceSampleSourceProbe {
  path: string;
  duration_seconds: number;
}

export interface AudioCleanerOption {
  id: string;
  description: string;
}

export interface EbookChapterSummary {
  id: number;
  title: string;
  order: number;
  word_count: number;
}

export interface LoadEbookResult {
  title: string;
  author: string | null;
  language: string | null;
  identifier: string | null;
  total_chapters: number;
  total_word_count: number;
  chapters: EbookChapterSummary[];
}

export interface ExtractTextResult {
  destination: string;
  total_chapters: number;
}

export interface ChapterEditDiff {
  id: number;
  title: string;
  diff: string;
}

export interface CopyEditResult {
  destination: string;
  chapters: ChapterEditDiff[];
}

export interface ExtractedTextSummary {
  path: string;
  title: string;
  author: string | null;
  chapter_count: number;
}

export interface GroupSource {
  type: string;
  identifier: string;
}

export interface GroupMember {
  path: string;
  // null = "in this series, but not numbered" (e.g. a side story) - never
  // meaningful for a standalone group's members.
  sequence: number | null;
}

export interface OrganizationGroup {
  id: string;
  name: string;
  // Fixed at creation - every member imports here, no picking needed later.
  library_id: string;
  folder_id: string;
  // True for the "no series" bucket: members still import to library_id/
  // folder_id, but no series name/sequence is ever attached to them.
  is_standalone: boolean;
  source: GroupSource | null;
  members: GroupMember[];
}

export interface LibraryFolder {
  id: string;
  path: string;
}

export interface MediaLibrarySummary {
  id: string;
  name: string;
  folders: LibraryFolder[];
}

export interface MediaLibraryItem {
  id: string;
  title: string;
  author: string | null;
  series: string | null;
  relative_path: string;
}

export interface ImportWorkRequest {
  group_id: string;
  source_path: string;
  title: string;
  author?: string | null;
}

export interface ImportWorkResult {
  destination_path: string;
}

export interface HealthCheckResult {
  healthy: boolean;
  detail: string;
}

export interface SyncSeriesResult {
  unlinked_series_names: string[];
}

export interface FolderHealth {
  folder_id: string;
  path: string;
  health: HealthCheckResult;
}

export interface HealthCheckLibraryResult {
  folders: FolderHealth[];
}

export interface MemberStatus {
  path: string;
  // The Audiobookshelf item id this member currently resolves to, live -
  // null means "not there right now", never cached locally.
  imported_item_id: string | null;
}

export interface GroupStatusResult {
  members: MemberStatus[];
}
