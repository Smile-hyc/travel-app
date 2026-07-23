package com.heoclub.aitravel.ui.components

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.ClickableText
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

private val BOLD_PATTERN = Regex("""\*\*(.+?)\*\*""")
private val ITALIC_PATTERN = Regex("""(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)""")
private val CODE_PATTERN = Regex("""`(.+?)`""")
private val LINK_PATTERN = Regex("""\[(.+?)]\((.+?)\)""")
private val BOLD_INTERNAL_LINK_PATTERN = Regex(
    """\*\*(\[[^\]\n]+]\(aitravel://place/[^)\s]+\))\*\*""",
)
private val UNDERSCORE_INTERNAL_LINK_PATTERN = Regex(
    """__(\[[^\]\n]+]\(aitravel://place/[^)\s]+\))__""",
)
private const val INTERNAL_PLACE_PREFIX = "aitravel://place/"

internal fun internalPlaceId(url: String): String? {
    if (!url.startsWith(INTERNAL_PLACE_PREFIX)) return null
    return URLDecoder.decode(
        url.removePrefix(INTERNAL_PLACE_PREFIX),
        StandardCharsets.UTF_8.name(),
    ).takeIf { it.isNotBlank() }
}

internal fun normalizeInternalPlaceLinks(text: String): String {
    return UNDERSCORE_INTERNAL_LINK_PATTERN.replace(
        BOLD_INTERNAL_LINK_PATTERN.replace(text, "$1"),
        "$1",
    )
}

@Composable
fun MarkdownText(
    text: String,
    modifier: Modifier = Modifier,
    style: TextStyle = MaterialTheme.typography.bodyLarge,
    color: Color = Color(0xFF162235),
    onInternalPlaceClick: ((String) -> Unit)? = null,
) {
    val context = LocalContext.current
    val lines = normalizeInternalPlaceLinks(text).split("\n")
    val baseStyle = style.copy(color = color)
    val headingStyle = baseStyle.copy(fontWeight = FontWeight.Bold)
    val codeBg = Color(0xFFF0F0F0)
    val linkColor = Color(0xFF1565C0)

    Column(modifier = modifier) {
        lines.forEachIndexed { index, line ->
            when {
                // Heading lines
                line.startsWith("### ") -> {
                    MarkdownLine(
                        text = parseInlineMarkdown(
                            line.removePrefix("### "),
                            baseStyle = headingStyle.copy(fontSize = (style.fontSize.value + 2).sp),
                            linkColor = linkColor,
                        ),
                        onInternalPlaceClick = onInternalPlaceClick,
                    )
                }
                line.startsWith("## ") -> {
                    MarkdownLine(
                        text = parseInlineMarkdown(
                            line.removePrefix("## "),
                            baseStyle = headingStyle.copy(fontSize = (style.fontSize.value + 4).sp),
                            linkColor = linkColor,
                        ),
                        onInternalPlaceClick = onInternalPlaceClick,
                    )
                }
                line.startsWith("# ") -> {
                    MarkdownLine(
                        text = parseInlineMarkdown(
                            line.removePrefix("# "),
                            baseStyle = headingStyle.copy(fontSize = (style.fontSize.value + 6).sp),
                            linkColor = linkColor,
                        ),
                        onInternalPlaceClick = onInternalPlaceClick,
                    )
                }
                // Unordered list items
                line.matches(Regex("""^[-*]\s.+""")) -> {
                    Row(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            text = "  •",
                            style = baseStyle,
                            color = color,
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        MarkdownLine(
                            text = parseInlineMarkdown(
                                line.removePrefix("- ").removePrefix("* "),
                                baseStyle = baseStyle,
                                linkColor = linkColor,
                            ),
                            onInternalPlaceClick = onInternalPlaceClick,
                        )
                    }
                }
                // Ordered list items
                line.matches(Regex("""^\d+\.\s.+""")) -> {
                    val number = line.substringBefore(".")
                    Row(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            text = "  $number.",
                            style = baseStyle,
                            color = color,
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        MarkdownLine(
                            text = parseInlineMarkdown(
                                line.substringAfter(". "),
                                baseStyle = baseStyle,
                                linkColor = linkColor,
                            ),
                            onInternalPlaceClick = onInternalPlaceClick,
                        )
                    }
                }
                // Blank line
                line.isBlank() -> {
                    Spacer(modifier = Modifier.height(8.dp))
                }
                // Regular paragraph line
                else -> {
                    MarkdownLine(
                        text = parseInlineMarkdown(line, baseStyle = baseStyle, linkColor = linkColor),
                        onInternalPlaceClick = onInternalPlaceClick,
                    )
                }
            }
        }
    }
}

@Composable
private fun MarkdownLine(
    text: AnnotatedString,
    modifier: Modifier = Modifier,
    onInternalPlaceClick: ((String) -> Unit)? = null,
) {
    val context = LocalContext.current
    val linkAnnotations = text.getStringAnnotations("URL", 0, text.length)

    if (linkAnnotations.isEmpty()) {
        Text(text = text, modifier = modifier)
    } else {
        ClickableText(
            text = text,
            modifier = modifier,
            onClick = { offset ->
                linkAnnotations.firstOrNull { offset in it.start until it.end }?.let { annotation ->
                    val placeId = internalPlaceId(annotation.item)
                    if (placeId != null && onInternalPlaceClick != null) {
                        onInternalPlaceClick(placeId)
                    } else {
                        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(annotation.item))
                        context.startActivity(intent)
                    }
                }
            },
        )
    }
}

private fun parseInlineMarkdown(
    text: String,
    baseStyle: TextStyle,
    linkColor: Color,
    codeBg: Color = Color(0xFFF0F0F0),
): AnnotatedString {
    // Split text into segments: normal text, bold (**...**), italic (*...*),
    // inline code (`...`), and links ([text](url)).
    // We process in order: code first (so `**` inside code isn't bold),
    // then links, then bold, then italic.

    // Collect all special spans with their positions
    data class Span(
        val start: Int,
        val end: Int,
        val type: String, // "bold", "italic", "code", "link"
        val content: String,
        val url: String? = null,
    )

    val spans = mutableListOf<Span>()

    // Find code spans first (to exclude from further processing)
    CODE_PATTERN.findAll(text).forEach { match ->
        spans.add(Span(match.range.first, match.range.last + 1, "code", match.groupValues[1]))
    }

    // Find links
    LINK_PATTERN.findAll(text).forEach { match ->
        val start = match.range.first
        val end = match.range.last + 1
        // Only add if not inside a code span
        if (spans.none { s -> s.type == "code" && start >= s.start && end <= s.end }) {
            spans.add(Span(start, end, "link", match.groupValues[1], match.groupValues[2]))
        }
    }

    // Find bold
    BOLD_PATTERN.findAll(text).forEach { match ->
        val start = match.range.first
        val end = match.range.last + 1
        if (spans.none { s -> start >= s.start && end <= s.end }) {
            spans.add(Span(start, end, "bold", match.groupValues[1]))
        }
    }

    // Find italic (only where not already inside bold, code, or link)
    ITALIC_PATTERN.findAll(text).forEach { match ->
        val start = match.range.first
        val end = match.range.last + 1
        if (spans.none { s -> start >= s.start && end <= s.end }) {
            // Also check it's not inside a bold span that we already found
            val boldSpans = spans.filter { it.type == "bold" }
            if (boldSpans.none { s -> start >= s.start && end <= s.end }) {
                spans.add(Span(start, end, "italic", match.groupValues[1]))
            }
        }
    }

    if (spans.isEmpty()) {
        return AnnotatedString(text, baseStyle.toSpanStyle())
    }

    // Sort spans by start position
    spans.sortBy { it.start }

    val annotated = buildAnnotatedString {
        var pos = 0
        for (span in spans) {
            // Add text before this span
            if (pos < span.start) {
                withStyle(baseStyle.toSpanStyle()) {
                    append(text.substring(pos, span.start))
                }
            }

            // Add the span content with appropriate style
            when (span.type) {
                "bold" -> {
                    withStyle(baseStyle.toSpanStyle().copy(fontWeight = FontWeight.Bold)) {
                        append(span.content)
                    }
                }
                "italic" -> {
                    withStyle(baseStyle.toSpanStyle().copy(fontStyle = FontStyle.Italic)) {
                        append(span.content)
                    }
                }
                "code" -> {
                    withStyle(
                        baseStyle.toSpanStyle().copy(
                            fontFamily = FontFamily.Monospace,
                            background = codeBg,
                            fontSize = baseStyle.fontSize * 0.9f,
                        )
                    ) {
                        append(span.content)
                    }
                }
                "link" -> {
                    pushStringAnnotation("URL", span.url ?: "")
                    withStyle(
                        baseStyle.toSpanStyle().copy(
                            color = linkColor,
                            fontWeight = FontWeight.SemiBold,
                            textDecoration = TextDecoration.Underline,
                        )
                    ) {
                        append(span.content)
                    }
                    pop()
                }
            }
            pos = span.end
        }

        // Add remaining text
        if (pos < text.length) {
            withStyle(baseStyle.toSpanStyle()) {
                append(text.substring(pos))
            }
        }
    }

    return annotated
}
