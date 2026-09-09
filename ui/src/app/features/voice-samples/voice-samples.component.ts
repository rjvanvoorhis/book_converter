import { Component, ElementRef, OnInit, ViewChild, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { FilePickerComponent } from '../../shared/file-picker/file-picker.component';
import { AudiobookApiService } from '../../core/audiobook-api.service';
import { VoiceSampleApiService } from '../../core/voice-sample-api.service';
import { DEFAULT_VOICE_SAMPLES_FOLDER } from '../../core/constants';
import { AudioCleanerOption, VoiceSampleSummary } from '../../core/models';

// Matches what pocket-tts-server documents as enough audio to clone a voice
// from - a sensible default clip length, not a hard limit.
const _DEFAULT_CLIP_SECONDS = 20;

const _SOURCE_AUDIO_EXTENSIONS = ['wav', 'mp3', 'm4a', 'flac', 'ogg', 'aac'];

@Component({
  selector: 'app-voice-samples',
  standalone: true,
  imports: [ReactiveFormsModule, FilePickerComponent],
  templateUrl: './voice-samples.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './voice-samples.component.css'
})
export class VoiceSamplesComponent implements OnInit {
  private readonly formBuilder = inject(FormBuilder);
  private readonly api = inject(VoiceSampleApiService);
  private readonly taskApi = inject(AudiobookApiService);

  @ViewChild('sourcePlayer') sourcePlayerRef?: ElementRef<HTMLAudioElement>;
  @ViewChild('previewPlayer') previewPlayerRef?: ElementRef<HTMLAudioElement>;

  readonly sourceExtensions = _SOURCE_AUDIO_EXTENSIONS;

  readonly sourcePath = this.formBuilder.nonNullable.control('');
  readonly sourceDuration = signal<number | null>(null);
  readonly sourceLoading = signal(false);
  readonly sourceError = signal<string | null>(null);

  readonly clipForm = this.formBuilder.nonNullable.group({
    startSeconds: [0, [Validators.required, Validators.min(0)]],
    durationSeconds: [_DEFAULT_CLIP_SECONDS, [Validators.required, Validators.min(0.5)]]
  });

  readonly cleanForm = this.formBuilder.nonNullable.group({
    clean: [true],
    cleaner: ['ffmpeg'],
    trimSilence: [true],
    normalizeLoudness: [true]
  });

  readonly cleaners = signal<AudioCleanerOption[]>([]);

  readonly outputFolder = this.formBuilder.nonNullable.control(DEFAULT_VOICE_SAMPLES_FOLDER);
  readonly sampleName = this.formBuilder.nonNullable.control('', Validators.required);

  readonly creating = signal(false);
  readonly createProgress = signal<string | null>(null);
  readonly createError = signal<string | null>(null);
  readonly createdSample = signal<VoiceSampleSummary | null>(null);

  readonly samples = signal<VoiceSampleSummary[]>([]);
  readonly samplesLoading = signal(false);
  readonly samplesError = signal<string | null>(null);

  readonly nowPlaying = signal<string | null>(null);
  readonly copiedPath = signal<string | null>(null);

  ngOnInit(): void {
    this.loadSamples();
    this.api.listCleaners().subscribe({
      next: (cleaners) => {
        this.cleaners.set(cleaners);
        // Prefer the highest-fidelity cleaner available - ffmpeg is the
        // only one guaranteed to be registered, so it's the fallback.
        const preferred = cleaners.find((c) => c.id === 'resemble-enhance') ?? cleaners[0];
        if (preferred) {
          this.cleanForm.patchValue({ cleaner: preferred.id });
        }
      }
    });
  }

  onSourcePicked(path: string): void {
    this.sourcePath.setValue(path);
    this.loadSource();
  }

  loadSource(): void {
    const path = this.sourcePath.value.trim();
    if (!path) {
      return;
    }
    this.sourceLoading.set(true);
    this.sourceError.set(null);
    this.sourceDuration.set(null);
    this.createdSample.set(null);
    this.api.probeSource(path).subscribe({
      next: (probe) => {
        this.sourceLoading.set(false);
        this.sourceDuration.set(probe.duration_seconds);
        this.clipForm.patchValue({ startSeconds: 0 });
        const player = this.sourcePlayerRef?.nativeElement;
        if (player) {
          player.src = this.api.getSourceAudioUrl(path);
          player.load();
        }
      },
      error: (err) => {
        this.sourceLoading.set(false);
        this.sourceError.set(_errorMessage(err));
      }
    });
  }

  // Scrubbing to the right spot in the full source player is the natural
  // way to find where a clean, well-spoken stretch starts - reading its
  // current position back in beats typing a timestamp by hand.
  useCurrentPositionAsStart(): void {
    const player = this.sourcePlayerRef?.nativeElement;
    if (!player) {
      return;
    }
    this.clipForm.patchValue({ startSeconds: Math.round(player.currentTime * 10) / 10 });
  }

  selectedCleanerDescription(): string {
    const selectedId = this.cleanForm.controls.cleaner.value;
    return this.cleaners().find((c) => c.id === selectedId)?.description ?? '';
  }

  clipEndSeconds(): number {
    const { startSeconds, durationSeconds } = this.clipForm.getRawValue();
    const end = startSeconds + durationSeconds;
    const total = this.sourceDuration();
    return total !== null ? Math.min(end, total) : end;
  }

  clipRangeValid(): boolean {
    const { startSeconds } = this.clipForm.getRawValue();
    const total = this.sourceDuration();
    return (
      this.clipForm.valid &&
      startSeconds >= 0 &&
      this.clipEndSeconds() > startSeconds &&
      (total === null || startSeconds < total)
    );
  }

  previewClip(): void {
    const path = this.sourcePath.value.trim();
    const player = this.previewPlayerRef?.nativeElement;
    if (!path || !player || !this.clipRangeValid()) {
      return;
    }
    const { startSeconds } = this.clipForm.getRawValue();
    const end = this.clipEndSeconds();
    this.nowPlaying.set(`Candidate clip @ ${startSeconds.toFixed(1)}s–${end.toFixed(1)}s (unprocessed)`);
    player.src = this.api.getSourceClipUrl(path, startSeconds, end);
    player.load();
    player.play();
  }

  createSample(): void {
    const path = this.sourcePath.value.trim();
    if (!path || !this.clipRangeValid() || this.sampleName.invalid) {
      return;
    }
    const { startSeconds } = this.clipForm.getRawValue();
    const end = this.clipEndSeconds();
    const { clean, cleaner, trimSilence, normalizeLoudness } = this.cleanForm.getRawValue();

    this.creating.set(true);
    this.createProgress.set(null);
    this.createError.set(null);
    this.createdSample.set(null);

    this.api
      .createSample({
        source_path: path,
        start_seconds: startSeconds,
        end_seconds: end,
        output_folder: this.outputFolder.value.trim() || DEFAULT_VOICE_SAMPLES_FOLDER,
        name: this.sampleName.value.trim(),
        clean,
        cleaner,
        trim_silence: trimSilence,
        normalize_loudness: normalizeLoudness
      })
      .subscribe({
        next: ({ task_id }) => {
          this.taskApi.pollTaskUntilDone<VoiceSampleSummary>(task_id).subscribe({
            next: (state) => {
              this.createProgress.set(state.message);
              if (state.status === 'completed' && state.result) {
                this.creating.set(false);
                this.createdSample.set(state.result);
                this.sampleName.setValue('');
                this.loadSamples();
                this.playSample(state.result);
              } else if (state.status === 'failed') {
                this.creating.set(false);
                this.createError.set(state.error ?? 'Cleaning failed.');
              }
            },
            error: (err) => {
              this.creating.set(false);
              this.createError.set(_errorMessage(err));
            }
          });
        },
        error: (err) => {
          this.creating.set(false);
          this.createError.set(_errorMessage(err));
        }
      });
  }

  loadSamples(): void {
    const folder = this.outputFolder.value.trim() || DEFAULT_VOICE_SAMPLES_FOLDER;
    this.samplesLoading.set(true);
    this.samplesError.set(null);
    this.api.listSamples(folder).subscribe({
      next: (samples) => {
        this.samplesLoading.set(false);
        this.samples.set(samples);
      },
      error: (err) => {
        this.samplesLoading.set(false);
        this.samplesError.set(_errorMessage(err));
      }
    });
  }

  playSample(sample: VoiceSampleSummary): void {
    const player = this.previewPlayerRef?.nativeElement;
    if (!player) {
      return;
    }
    this.nowPlaying.set(`${sample.name} (${sample.duration_seconds.toFixed(1)}s, cleaned)`);
    player.src = this.api.getSampleAudioUrl(sample.path);
    player.load();
    player.play();
  }

  deleteSample(sample: VoiceSampleSummary): void {
    this.api.deleteSample(sample.path).subscribe({
      next: () => this.loadSamples()
    });
  }

  copyPath(path: string): void {
    navigator.clipboard?.writeText(path).then(() => {
      this.copiedPath.set(path);
      setTimeout(() => {
        if (this.copiedPath() === path) {
          this.copiedPath.set(null);
        }
      }, 1500);
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
