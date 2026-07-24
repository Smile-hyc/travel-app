package com.heoclub.aitravel.ui.journey

import android.graphics.Bitmap
import androidx.compose.ui.graphics.Color
import java.time.LocalDate

internal data class JournalPhoto(
    val bitmap: Bitmap? = null,
    val label: String,
    val color: Color,
)

internal data class JournalTextStyle(
    val bold: Boolean = false,
    val underline: Boolean = false,
    val highlighted: Boolean = false,
    val textColor: Color = Color(0xFF26384D),
    val highlightColor: Color = Color(0xFFFFF0A8),
)

internal data class JournalEntry(
    val id: String,
    val date: LocalDate,
    val title: String,
    val titleColor: Color = Color(0xFF081F3A),
    val titleStyle: JournalTextStyle = JournalTextStyle(bold = true, textColor = titleColor),
    val location: String,
    val body: String,
    val bodyStyle: JournalTextStyle = JournalTextStyle(),
    val photos: List<JournalPhoto>,
)

internal val seedJournalEntries = listOf(
    JournalEntry(
        id = "seed-hangzhou-westlake",
        date = LocalDate.of(2026, 7, 4),
        title = "西湖慢行路线",
        location = "杭州市",
        body = "断桥到苏堤适合步行，沿湖一圈的节奏不用太赶。下午可以把灵隐寺和龙井村放进备选。",
        photos = listOf(
            JournalPhoto(label = "湖岸", color = Color(0xFF9FD7EA)),
            JournalPhoto(label = "茶园", color = Color(0xFFA9D9AE)),
            JournalPhoto(label = "苏堤", color = Color(0xFFEFD083)),
            JournalPhoto(label = "夜色", color = Color(0xFF8FA8D8)),
        ),
    ),
    JournalEntry(
        id = "seed-chengdu-panda",
        date = LocalDate.of(2026, 6, 16),
        title = "熊猫基地半日",
        location = "成都市",
        body = "早上入园体验最好，人少也凉快。看完幼年熊猫后回市区，下午接人民公园喝茶。",
        photos = listOf(
            JournalPhoto(label = "熊猫基地", color = Color(0xFFB6D8C2)),
        ),
    ),
    JournalEntry(
        id = "seed-beijing-palace",
        date = LocalDate.of(2026, 5, 28),
        title = "故宫午后路线",
        location = "北京市",
        body = "午门进、神武门出，角楼日落值得单独留时间。展厅不要贪多，选两三个重点就够。",
        photos = emptyList(),
    ),
    JournalEntry(
        id = "seed-guangzhou-food",
        date = LocalDate.of(2026, 4, 12),
        title = "荔湾早茶和骑楼",
        location = "广州市",
        body = "老城区适合慢慢走，早茶后顺路看骑楼，下午去沙面比较舒服。",
        photos = listOf(
            JournalPhoto(label = "早茶", color = Color(0xFFF1C987)),
            JournalPhoto(label = "骑楼", color = Color(0xFFC9D4E8)),
        ),
    ),
)
