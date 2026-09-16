import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { AuditApiService } from '../../core/audit-api.service';
import { MediaLibraryApiService } from '../../core/media-library-api.service';
import { OrganizationApiService } from '../../core/organization-api.service';
import { DEFAULT_AUDIOBOOK_FOLDER } from '../../core/constants';
import {
  AudiobookSummary,
  FolderHealth,
  GroupMember,
  LibraryFolder,
  MediaLibrarySummary,
  MemberStatus,
  OrganizationGroup
} from '../../core/models';

@Component({
  selector: 'app-organization',
  standalone: true,
  imports: [ReactiveFormsModule],
  templateUrl: './organization.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './organization.component.css'
})
export class OrganizationComponent implements OnInit {
  private readonly formBuilder = inject(FormBuilder);
  private readonly auditApi = inject(AuditApiService);
  private readonly organizationApi = inject(OrganizationApiService);
  private readonly mediaLibraryApi = inject(MediaLibraryApiService);

  readonly audiobooks = signal<AudiobookSummary[]>([]);
  readonly groups = signal<OrganizationGroup[]>([]);
  readonly unassignedPaths = signal<string[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  // Libraries are fetched lazily (first time anything needs them) and
  // cached, since listing them means a real round trip to the configured
  // Audiobookshelf server.
  readonly libraries = signal<MediaLibrarySummary[] | null>(null);
  readonly librariesLoading = signal(false);
  readonly librariesError = signal<string | null>(null);

  // Top-of-page library context: drives the folder-health display and
  // "discover unlinked series" below, and pre-selects the library for the
  // new-series form (which still requires its own explicit choice - a
  // series's library/folder is never implied silently).
  readonly selectedLibraryId = signal('');
  readonly libraryHealth = signal<FolderHealth[] | null>(null);
  readonly libraryHealthLoading = signal(false);
  readonly libraryHealthError = signal<string | null>(null);
  readonly registeringFolderId = signal<string | null>(null);

  readonly unlinkedSeriesNames = signal<string[] | null>(null);
  readonly unlinkedSeriesLoading = signal(false);
  readonly unlinkedSeriesError = signal<string | null>(null);

  // A series MUST be bound to a library/folder from the moment it's
  // created - there's no "create now, assign later" path.
  readonly newGroupForm = this.formBuilder.nonNullable.group({
    name: ['', Validators.required],
    libraryId: ['', Validators.required],
    folderId: ['', Validators.required],
    isStandalone: [false]
  });

  // Whether each group's members are actually present in Audiobookshelf
  // right now - checked live, per group, never cached beyond this session.
  readonly statusByGroupId = signal<Record<string, MemberStatus[]>>({});
  readonly statusLoadingGroupId = signal<string | null>(null);
  readonly importingPath = signal<string | null>(null);
  readonly importError = signal<string | null>(null);
  // Import triggers an Audiobookshelf scan, which runs async server-side -
  // the item usually isn't visible via groupStatus the instant the import
  // call returns, so this polls for a bit afterward instead of checking
  // once and reporting a false "not imported".
  readonly verifyingPath = signal<string | null>(null);
  private static readonly _POLL_INTERVAL_MS = 2000;
  private static readonly _POLL_MAX_ATTEMPTS = 15; // ~30s total

  // Unlisted panel: bulk-assign UI - a checkbox per row, one "assign to"
  // target picked once in the header, and either an individual "Assign" per
  // row or a header "Assign N Works" once at least one is checked.
  readonly unlistedTargetGroupId = signal('');
  readonly checkedUnlistedPaths = signal<Set<string>>(new Set());
  readonly assigning = signal(false);

  // HTML5 drag-and-drop state for reordering a group's numbered members.
  readonly draggingPath = signal<string | null>(null);

  ngOnInit(): void {
    this.loadAll();
    this.ensureLibrariesLoaded();
  }

  loadAll(): void {
    this.loading.set(true);
    this.error.set(null);
    this.auditApi.listAudiobooks(DEFAULT_AUDIOBOOK_FOLDER).subscribe({
      next: (audiobooks) => {
        this.audiobooks.set(audiobooks);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(_errorMessage(err));
        this.loading.set(false);
      }
    });
    this.organizationApi.listGroups().subscribe({
      next: (groups) => {
        this.groups.set(groups);
        for (const group of groups) {
          this.refreshGroupStatus(group.id);
        }
      }
    });
    this.organizationApi.listUnassigned(DEFAULT_AUDIOBOOK_FOLDER).subscribe({
      next: (paths) => this.unassignedPaths.set(paths)
    });
  }

  titleFor(path: string): string {
    return this.audiobooks().find((item) => item.path === path)?.title ?? path;
  }

  libraryNameFor(libraryId: string): string {
    return this.libraries()?.find((library) => library.id === libraryId)?.name ?? libraryId;
  }

  folderPathFor(libraryId: string, folderId: string): string {
    const folder = this.libraries()
      ?.find((library) => library.id === libraryId)
      ?.folders.find((f) => f.id === folderId);
    return folder?.path ?? folderId;
  }

  // ---- Libraries / health --------------------------------------------

  ensureLibrariesLoaded(): void {
    if (this.libraries() !== null || this.librariesLoading()) {
      return;
    }
    this.librariesLoading.set(true);
    this.librariesError.set(null);
    this.mediaLibraryApi.listLibraries().subscribe({
      next: (libraries) => {
        this.libraries.set(libraries);
        this.librariesLoading.set(false);
      },
      error: (err) => {
        this.librariesError.set(_errorMessage(err));
        this.librariesLoading.set(false);
      }
    });
  }

  setSelectedLibrary(libraryId: string): void {
    this.selectedLibraryId.set(libraryId);
    this.libraryHealth.set(null);
    this.libraryHealthError.set(null);
    this.unlinkedSeriesNames.set(null);
    this.unlinkedSeriesError.set(null);
    if (libraryId) {
      this.checkSelectedLibraryHealth();
      this.discoverUnlinkedSeries();
    }
  }

  checkSelectedLibraryHealth(): void {
    const libraryId = this.selectedLibraryId();
    if (!libraryId) {
      return;
    }
    this.libraryHealthLoading.set(true);
    this.libraryHealthError.set(null);
    this.mediaLibraryApi.healthCheckLibrary(libraryId).subscribe({
      next: (result) => {
        this.libraryHealthLoading.set(false);
        this.libraryHealth.set(result.folders);
      },
      error: (err) => {
        this.libraryHealthLoading.set(false);
        this.libraryHealthError.set(_errorMessage(err));
      }
    });
  }

  registerFolder(folderId: string): void {
    const libraryId = this.selectedLibraryId();
    if (!libraryId) {
      return;
    }
    this.registeringFolderId.set(folderId);
    this.mediaLibraryApi.registerFolder(libraryId, folderId).subscribe({
      next: (health) => {
        this.registeringFolderId.set(null);
        this.libraryHealth.update((current) =>
          (current ?? []).map((folder) =>
            folder.folder_id === folderId ? { ...folder, health } : folder
          )
        );
      },
      error: (err) => {
        this.registeringFolderId.set(null);
        this.libraryHealthError.set(_errorMessage(err));
      }
    });
  }

  discoverUnlinkedSeries(): void {
    const libraryId = this.selectedLibraryId();
    if (!libraryId) {
      return;
    }
    this.unlinkedSeriesLoading.set(true);
    this.unlinkedSeriesError.set(null);
    this.mediaLibraryApi.unlinkedSeries(libraryId).subscribe({
      next: (names) => {
        this.unlinkedSeriesLoading.set(false);
        this.unlinkedSeriesNames.set(names);
      },
      error: (err) => {
        this.unlinkedSeriesLoading.set(false);
        this.unlinkedSeriesError.set(_errorMessage(err));
      }
    });
  }

  // ---- New series form --------------------------------------------

  foldersForLibrary(libraryId: string): LibraryFolder[] {
    return this.libraries()?.find((library) => library.id === libraryId)?.folders ?? [];
  }

  setNewGroupLibrary(libraryId: string): void {
    this.newGroupForm.patchValue({ libraryId, folderId: '' });
  }

  createGroup(): void {
    if (this.newGroupForm.invalid) {
      return;
    }
    const { name, libraryId, folderId, isStandalone } = this.newGroupForm.getRawValue();
    this.organizationApi.createGroup(name, libraryId, folderId, isStandalone).subscribe({
      next: () => {
        this.newGroupForm.reset({
          name: '',
          libraryId: '',
          folderId: '',
          isStandalone: false
        });
        this.loadAll();
      },
      error: (err) => this.error.set(_errorMessage(err))
    });
  }

  deleteGroup(group: OrganizationGroup): void {
    this.organizationApi.deleteGroup(group.id).subscribe({ next: () => this.loadAll() });
  }

  // ---- Group members: sequence editing + drag reorder -----------------

  orderedMembers(group: OrganizationGroup): GroupMember[] {
    return group.members.filter((m) => m.sequence !== null);
  }

  unorderedMembers(group: OrganizationGroup): GroupMember[] {
    return group.members.filter((m) => m.sequence === null);
  }

  setMemberSequence(group: OrganizationGroup, path: string, rawValue: string): void {
    const sequence = rawValue.trim() === '' ? null : Number(rawValue);
    this.organizationApi.addMember(group.id, path, sequence).subscribe({
      next: () => this.loadAll()
    });
  }

  removeMember(group: OrganizationGroup, path: string): void {
    this.organizationApi.removeMember(group.id, path).subscribe({ next: () => this.loadAll() });
  }

  onDragStart(path: string): void {
    this.draggingPath.set(path);
  }

  onDragEnd(): void {
    this.draggingPath.set(null);
  }

  onDropOnto(group: OrganizationGroup, targetPath: string): void {
    const dragging = this.draggingPath();
    this.draggingPath.set(null);
    if (!dragging || dragging === targetPath) {
      return;
    }
    const ordered = this.orderedMembers(group).map((m) => m.path);
    const fromIndex = ordered.indexOf(dragging);
    const toIndex = ordered.indexOf(targetPath);
    if (fromIndex === -1 || toIndex === -1) {
      return;
    }
    ordered.splice(fromIndex, 1);
    ordered.splice(toIndex, 0, dragging);
    this.organizationApi.reorderMembers(group.id, ordered).subscribe({
      next: () => this.loadAll()
    });
  }

  // ---- Import / re-sync + live status --------------------------------

  refreshGroupStatus(groupId: string): void {
    this.statusLoadingGroupId.set(groupId);
    this.mediaLibraryApi.groupStatus(groupId).subscribe({
      next: (result) => {
        this.statusLoadingGroupId.set(null);
        this.statusByGroupId.update((current) => ({ ...current, [groupId]: result.members }));
      },
      error: () => {
        this.statusLoadingGroupId.set(null);
      }
    });
  }

  importedItemIdFor(groupId: string, path: string): string | null {
    return (
      this.statusByGroupId()[groupId]?.find((status) => status.path === path)
        ?.imported_item_id ?? null
    );
  }

  importWork(group: OrganizationGroup, path: string): void {
    this.importError.set(null);
    this.importingPath.set(path);
    this.mediaLibraryApi
      .importWork({ group_id: group.id, source_path: path, title: this.titleFor(path) })
      .subscribe({
        next: () => {
          this.importingPath.set(null);
          this.pollForImportStatus(group.id, path, 1);
        },
        error: (err) => {
          this.importingPath.set(null);
          this.importError.set(_errorMessage(err));
        }
      });
  }

  isVerifying(path: string): boolean {
    return this.verifyingPath() === path;
  }

  /** Polls groupStatus until this path shows up as imported, or gives up
   * after a bounded number of attempts - Audiobookshelf's scan runs async,
   * so the item is rarely there on the very first check right after
   * import. Also used to double-check an item that already looked
   * unimported, in case a scan from some earlier action is still catching
   * up. */
  private pollForImportStatus(groupId: string, path: string, attempt: number): void {
    this.verifyingPath.set(path);
    this.mediaLibraryApi.groupStatus(groupId).subscribe({
      next: (result) => {
        this.statusByGroupId.update((current) => ({ ...current, [groupId]: result.members }));
        const found = !!result.members.find((m) => m.path === path)?.imported_item_id;
        if (found || attempt >= OrganizationComponent._POLL_MAX_ATTEMPTS) {
          this.verifyingPath.set(null);
          return;
        }
        setTimeout(
          () => this.pollForImportStatus(groupId, path, attempt + 1),
          OrganizationComponent._POLL_INTERVAL_MS
        );
      },
      error: () => this.verifyingPath.set(null)
    });
  }

  // ---- Unlisted panel: bulk assign -----------------------------------

  setUnlistedTargetGroup(groupId: string): void {
    this.unlistedTargetGroupId.set(groupId);
  }

  isChecked(path: string): boolean {
    return this.checkedUnlistedPaths().has(path);
  }

  toggleChecked(path: string): void {
    this.checkedUnlistedPaths.update((current) => {
      const next = new Set(current);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }

  assignSingle(path: string): void {
    this.assignPaths([path]);
  }

  assignChecked(): void {
    this.assignPaths([...this.checkedUnlistedPaths()]);
  }

  private assignPaths(paths: string[]): void {
    const groupId = this.unlistedTargetGroupId();
    if (!groupId || paths.length === 0) {
      return;
    }
    const group = this.groups().find((g) => g.id === groupId);
    const startSequence = (group?.members.filter((m) => m.sequence !== null).length ?? 0) + 1;

    this.assigning.set(true);
    let remaining = paths.length;
    let failed = false;
    paths.forEach((path, index) => {
      const sequence = group?.is_standalone ? null : startSequence + index;
      this.organizationApi.addMember(groupId, path, sequence).subscribe({
        next: () => {
          remaining -= 1;
          if (remaining === 0) {
            this.assigning.set(false);
            this.checkedUnlistedPaths.set(new Set());
            this.loadAll();
          }
        },
        error: (err) => {
          remaining -= 1;
          if (!failed) {
            failed = true;
            this.error.set(_errorMessage(err));
          }
          if (remaining === 0) {
            this.assigning.set(false);
            this.loadAll();
          }
        }
      });
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
