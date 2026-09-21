import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

/// A file the user chose, already in memory and ready to POST.
///
/// Bytes rather than a path on purpose: the web build has no filesystem, and
/// on Android a content:// URI from the gallery is not a path either. Every
/// upload in the app goes through [ApiClient.upload], which wants bytes.
class PickedUpload {
  const PickedUpload(this.name, this.bytes);

  final String name;
  final List<int> bytes;

  int get sizeKb => (bytes.length / 1024).round();
}

/// Ask where the file is coming from, then get it.
///
/// The camera is first because it is what the job actually is: a BDE standing
/// on somebody's roof photographing a meter box, not browsing a file manager.
/// Returns an empty list if they backed out.
Future<List<PickedUpload>> pickUploads(
  BuildContext context, {
  bool allowMultiple = true,
  bool imagesOnly = false,
}) async {
  final source = await showModalBottomSheet<String>(
    context: context,
    builder: (context) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(height: 6),
          ListTile(
            leading: const Icon(Icons.photo_camera_outlined),
            title: const Text('Take a photo'),
            onTap: () => Navigator.pop(context, 'camera'),
          ),
          ListTile(
            leading: const Icon(Icons.photo_library_outlined),
            title: Text(allowMultiple ? 'Choose photos' : 'Choose a photo'),
            onTap: () => Navigator.pop(context, 'gallery'),
          ),
          if (!imagesOnly)
            ListTile(
              leading: const Icon(Icons.folder_outlined),
              title: Text(allowMultiple ? 'Choose files' : 'Choose a file'),
              subtitle: const Text('PDFs, documents, anything else'),
              onTap: () => Navigator.pop(context, 'files'),
            ),
          const SizedBox(height: 10),
        ],
      ),
    ),
  );
  if (source == null) return const [];

  final picker = ImagePicker();
  switch (source) {
    case 'camera':
      final shot = await picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 85,
        maxWidth: 2400,
      );
      if (shot == null) return const [];
      return [
        PickedUpload(_named(shot.name, 'photo.jpg'), await shot.readAsBytes()),
      ];

    case 'gallery':
      if (!allowMultiple) {
        final one = await picker.pickImage(
          source: ImageSource.gallery,
          imageQuality: 85,
          maxWidth: 2400,
        );
        if (one == null) return const [];
        return [
          PickedUpload(_named(one.name, 'photo.jpg'), await one.readAsBytes()),
        ];
      }
      final many = await picker.pickMultiImage(
        imageQuality: 85,
        maxWidth: 2400,
      );
      return [
        for (final x in many)
          PickedUpload(_named(x.name, 'photo.jpg'), await x.readAsBytes()),
      ];

    default:
      final files = allowMultiple
          ? await FilePicker.pickFiles()
          : [?await FilePicker.pickFile()];
      return [
        for (final f in files)
          PickedUpload(_named(f.name, 'file'), await f.readAsBytes()),
      ];
  }
}

String _named(String candidate, String fallback) {
  final name = candidate.split('/').last.trim();
  return name.isEmpty ? fallback : name;
}
