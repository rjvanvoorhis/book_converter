import {
  Component,
  OnDestroy,
  OnInit,
  inject,
  signal,
  ChangeDetectionStrategy
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { AudiobookApiService } from '../../core/audiobook-api.service';
import { PronunciationApiService } from '../../core/pronunciation-api.service';
import {
  BOOK_SOURCES,
  DEFAULT_AUDIOBOOK_FOLDER,
  DEFAULT_PRONUNCIATIONS_FOLDER,
  TTS_PROVIDERS
} from '../../core/constants';
import { AudiobookTaskState, PronunciationDictSummary, VoiceProfile } from '../../core/models';
import { FilePickerComponent } from '../../shared/file-picker/file-picker.component';

@Component({
  selector: 'app-create-audiobook',
  standalone: true,
  imports: [ReactiveFormsModule, FilePickerComponent],
  templateUrl: './create-audiobook.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './create-audiobook.component.css'
})
export class CreateAudiobookComponent implements OnInit, OnDestroy {
  private readonly formBuilder = inject(FormBuilder);
  private readonly api = inject(AudiobookApiService);
  private readonly pronunciationApi = inject(PronunciationApiService);

  readonly sources = BOOK_SOURCES;
  readonly ttsProviders = TTS_PROVIDERS;

  readonly pronunciationDicts = signal<PronunciationDictSummary[]>([]);

  readonly voices = signal<VoiceProfile[]>([]);
  readonly voicesLoading = signal(false);
  readonly voicesError = signal<string | null>(null);

  readonly submitting = signal(false);
  readonly submitError = signal<string | null>(null);
  readonly task = signal<AudiobookTaskState | null>(null);
  readonly taskId = signal<string | null>(null);

  readonly advancedOpen = signal(false);

  readonly sampleTask = signal<AudiobookTaskState | null>(null);
  readonly sampleTaskId = signal<string | null>(null);
  readonly sampleError = signal<string | null>(null);
  readonly sampleAudioUrl = signal<string | null>(null);

  readonly form = this.formBuilder.nonNullable.group({
    source: ['file', Validators.required],
    identifier: ['', Validators.required],
    name: ['', Validators.required],
    audiobookFolder: [DEFAULT_AUDIOBOOK_FOLDER, Validators.required],
    ttsProvider: ['pocket-tts', Validators.required],
    engine: ['pocket-tts', Validators.required],
    voice: ['', Validators.required],
    dialogueVoice: [''],
    pronunciations: [''],
    addPauses: [false],
    batchSize: [1, [Validators.required, Validators.min(1)]],
    chaptersPerChunk: [null as number | null],
    sampleSentenceCount: [3, [Validators.required, Validators.min(1)]]
  });

  ngOnInit(): void {
    this.loadVoices();
    this.pronunciationApi.listDictionaries(DEFAULT_PRONUNCIATIONS_FOLDER).subscribe({
      next: (dicts) => this.pronunciationDicts.set(dicts)
    });
  }

  ngOnDestroy(): void {
    const url = this.sampleAudioUrl();
    if (url) {
      URL.revokeObjectURL(url);
    }
  }

  onProviderChange(): void {
    // The engine value only matters to the Kokoro provider (it's sent as the
    // synthesis model); defaulting it to the provider id keeps the field
    // sensible without making users think about it for pocket-tts.
    this.form.controls.engine.setValue(this.form.controls.ttsProvider.value);
    this.loadVoices();
  }

  onEngineChange(): void {
    this.loadVoices();
  }

  loadVoices(): void {
    const { engine, ttsProvider } = this.form.getRawValue();
    if (!engine || !ttsProvider) {
      return;
    }

    this.voicesLoading.set(true);
    this.voicesError.set(null);
    this.api.listVoices(engine, ttsProvider).subscribe({
      next: (voices) => {
        this.voices.set(voices);
        this.voicesLoading.set(false);

        const currentVoice = this.form.controls.voice.value;
        if (!voices.some((voice) => voice.id === currentVoice)) {
          this.form.controls.voice.setValue(voices[0]?.id ?? '');
        }
      },
      error: (err) => {
        this.voices.set([]);
        this.voicesLoading.set(false);
        this.voicesError.set(_errorMessage(err));
      }
    });
  }

  toggleAdvanced(): void {
    this.advancedOpen.update((open) => !open);
  }

  identifierPlaceholder(): string {
    const source = this.form.controls.source.value;
    return this.sources.find((option) => option.value === source)?.identifierPlaceholder ?? '';
  }

  isFileSource(): boolean {
    return this.form.controls.source.value === 'file';
  }

  onFilePicked(path: string): void {
    this.form.controls.identifier.setValue(path);
  }

  isTaskInProgress(): boolean {
    const status = this.task()?.status;
    return status === 'pending' || status === 'running';
  }

  submitButtonLabel(): string {
    if (this.submitting()) {
      return 'Starting…';
    }
    if (this.isTaskInProgress()) {
      return 'Generating…';
    }
    return 'Create audiobook';
  }

  isSampleInProgress(): boolean {
    const status = this.sampleTask()?.status;
    return status === 'pending' || status === 'running';
  }

  sampleButtonLabel(): string {
    return this.isSampleInProgress() ? 'Generating…' : 'Preview sample';
  }

  cancelSample(): void {
    const taskId = this.sampleTaskId();
    if (taskId) {
      this.api.cancelTask(taskId).subscribe();
    }
  }

  cancelTask(): void {
    const taskId = this.taskId();
    if (taskId) {
      this.api.cancelTask(taskId).subscribe();
    }
  }

  generateSample(): void {
    const { identifier, source, ttsProvider, engine, voice, sampleSentenceCount, pronunciations, addPauses } =
      this.form.getRawValue();
    if (!identifier || !voice) {
      this.sampleError.set('Enter an identifier and choose a voice first.');
      return;
    }

    this.sampleError.set(null);
    this.sampleTask.set(null);
    const previousUrl = this.sampleAudioUrl();
    if (previousUrl) {
      URL.revokeObjectURL(previousUrl);
      this.sampleAudioUrl.set(null);
    }

    this.api
      .createSample({
        identifier,
        source,
        tts_provider: ttsProvider,
        engine,
        voice,
        sentence_count: sampleSentenceCount,
        pronunciations: pronunciations || null,
        add_pauses: addPauses
      })
      .subscribe({
        next: ({ task_id }) => {
          this.sampleTaskId.set(task_id);
          this.api.pollTaskUntilDone(task_id).subscribe({
            next: (state) => {
              this.sampleTask.set(state);
              if (state.status === 'completed') {
                this.api.getSampleAudio(task_id).subscribe({
                  next: (blob) => this.sampleAudioUrl.set(URL.createObjectURL(blob)),
                  error: (err) => this.sampleError.set(_errorMessage(err))
                });
              } else if (state.status === 'failed') {
                this.sampleError.set(state.error ?? 'Sample generation failed.');
              }
            },
            error: (err) => this.sampleError.set(_errorMessage(err))
          });
        },
        error: (err) => this.sampleError.set(_errorMessage(err))
      });
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    this.submitting.set(true);
    this.submitError.set(null);
    this.task.set(null);

    this.api
      .createAudiobook({
        identifier: value.identifier,
        name: value.name,
        audiobook_folder: value.audiobookFolder,
        source: value.source,
        tts_provider: value.ttsProvider,
        engine: value.engine,
        voice: value.voice,
        dialogue_voice: value.dialogueVoice || null,
        pronunciations: value.pronunciations || null,
        add_pauses: value.addPauses,
        batch_size: value.batchSize,
        chapters_per_chunk: value.chaptersPerChunk
      })
      .subscribe({
        next: ({ task_id }) => {
          this.submitting.set(false);
          this.taskId.set(task_id);
          this.api.pollTaskUntilDone(task_id).subscribe({
            next: (state) => this.task.set(state),
            error: (err) => this.submitError.set(_errorMessage(err))
          });
        },
        error: (err) => {
          this.submitting.set(false);
          this.submitError.set(_errorMessage(err));
        }
      });
  }
}

function _errorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'error' in err) {
    const body = (err as { error?: unknown }).error;
    if (body && typeof body === 'object' && 'error' in body) {
      return String((body as { error?: unknown }).error);
    }
  }
  return 'Request failed. Is the API server running?';
}
