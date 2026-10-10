import { Editor } from "@tinymce/tinymce-react";

export type RichTextEditorProps = {
  value: string;
  onChange: (value: string) => void;
  height?: number;
  placeholder?: string;
};

export function RichTextEditor({ value, onChange, height = 250, placeholder }: RichTextEditorProps) {
  return (
    <Editor
      tinymceScriptSrc="/tinymce/tinymce.min.js"
      value={value}
      onEditorChange={(content) => onChange(content)}
      init={{
        height,
        menubar: true,
        placeholder,
        plugins: [
          "advlist",
          "autolink",
          "lists",
          "link",
          "image",
          "charmap",
          "preview",
          "anchor",
          "searchreplace",
          "visualblocks",
          "code",
          "fullscreen",
          "insertdatetime",
          "media",
          "table",
          "help",
          "wordcount",
        ],
        toolbar:
          "undo redo | blocks | " +
          "bold italic forecolor | alignleft aligncenter " +
          "alignright alignjustify | bullist numlist outdent indent | " +
          "table | link | removeformat | help",
        content_style:
          "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 13px; line-height: 1.6; color: #344138; }",
      }}
    />
  );
}
