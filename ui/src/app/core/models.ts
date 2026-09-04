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
