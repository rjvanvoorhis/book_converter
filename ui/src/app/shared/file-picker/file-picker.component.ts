import { Component, EventEmitter, Input, Output, inject, signal, ChangeDetectionStrategy } from '@angular/core';

import { FileBrowserApiService } from '../../core/file-browser-api.service';
import { FileBrowserEntry } from '../../core/models';

@Component({
  selector: 'app-file-picker',
  standalone: true,
  imports: [],
  templateUrl: './file-picker.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './file-picker.component.css'
})
export class FilePickerComponent {
  private readonly api = inject(FileBrowserApiService);

  /** Directory to open the browser in, e.g. the current identifier's folder. */
  @Input() startPath?: string;
  @Output() fileSelected = new EventEmitter<string>();

  readonly open = signal(false);
  readonly path = signal<string | null>(null);
  readonly parent = signal<string | null>(null);
  readonly entries = signal<FileBrowserEntry[]>([]);
  readonly error = signal<string | null>(null);

  toggle(): void {
    if (this.open()) {
      this.open.set(false);
      return;
    }
    this.open.set(true);
    this.browse(this.startPath);
  }

  browse(path?: string): void {
    this.error.set(null);
    this.api.browse(path).subscribe({
      next: (listing) => {
        this.path.set(listing.path);
        this.parent.set(listing.parent);
        this.entries.set(listing.entries);
      },
      error: (err) => this.error.set(_errorMessage(err))
    });
  }

  navigateUp(): void {
    const parent = this.parent();
    if (parent) {
      this.browse(parent);
    }
  }

  select(entry: FileBrowserEntry): void {
    if (entry.is_dir) {
      this.browse(entry.path);
    } else {
      this.fileSelected.emit(entry.path);
      this.open.set(false);
    }
  }
}

function _errorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'error' in err) {
    const body = (err as { error?: unknown }).error;
    if (body && typeof body === 'object' && 'error' in body) {
      return String((body as { error?: unknown }).error);
    }
  }
  return 'Could not browse this folder.';
}
