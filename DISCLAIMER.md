# Disclaimer

ZeroTrace Engine is a local-first file and registry review tool. It is designed to make cleanup candidates visible, confirmable, reversible where possible, and auditable.

This project does not guarantee that every scan result is safe to remove. System behavior, application data, registry entries, and user files can vary by device, Windows version, installed software, and user configuration.

## User Responsibility

- Review every scan result before creating or running a cleanup plan.
- Confirm that selected files, folders, or registry entries are no longer needed.
- Keep your own backups of important data before using cleanup or registry features.
- Use registry cleanup features only when you understand the possible impact.

## File Operations

ZeroTrace Engine moves approved file cleanup items into the project recycle area first whenever possible. Restore support is provided for items tracked by the application, but recovery is not guaranteed in every situation, especially if files are changed, moved, deleted, locked, or modified by other software.

When removing items from the recycle page, Windows may move files to the system Recycle Bin when supported. On other systems, removal may be direct deletion.

## Registry Operations

Registry scan results are suggestions for review, not automatic repair advice. Editing or removing registry entries can affect Windows, installed applications, startup behavior, file associations, services, and user settings.

ZeroTrace Engine may export `.reg` backups before registry cleanup operations, but successful restoration depends on system permissions, registry state, and Windows behavior.

## No Warranty

This software is provided as-is, without warranty of any kind. The author is not responsible for data loss, system instability, application issues, registry damage, or other direct or indirect consequences caused by using this project.

Use ZeroTrace Engine carefully, and always prefer safety over convenience.
