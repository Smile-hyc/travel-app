package com.heoclub.aitravel.data.repository

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.heoclub.aitravel.data.model.AiSuggestedAction
import com.heoclub.aitravel.data.model.AiPlanGenerationResponse
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.data.model.PlanDay
import com.heoclub.aitravel.data.model.PlanItem
import com.heoclub.aitravel.data.model.RoutePlace
import com.heoclub.aitravel.data.model.TravelPlan
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.util.UUID

private const val UNPLANNED_DAY_ID = "unplanned"
private const val UNPLANNED_DAY_INDEX = 0

interface TravelPlanRepository {
    val plans: StateFlow<List<TravelPlan>>

    fun createPlan(
        destination: String,
        dateRange: String,
        preferences: List<String>,
        dayCount: Int? = null,
    ): TravelPlan

    fun importGeneratedPlan(generated: AiPlanGenerationResponse): TravelPlan

    fun getPlan(planId: String): TravelPlan?

    fun deletePlan(planId: String): Boolean

    fun addPlaceToPlan(
        planId: String,
        place: PlaceSummary,
        target: AddPlaceTarget = AddPlaceTarget.Day(1),
    ): AddPlaceResult

    fun moveUnplannedItemToDay(
        planId: String,
        itemId: String,
        dayIndex: Int,
    ): AddPlaceResult

    fun movePlanItem(
        planId: String,
        dayIndex: Int,
        itemId: String,
        direction: MoveDirection,
    )

    fun applyOptimizedOrder(
        planId: String,
        dayIndex: Int,
        orderedPlaceIds: List<String>,
    )

    fun applyAiSuggestedActions(
        planId: String,
        expectedRevision: Long?,
        actions: List<AiSuggestedAction>,
    ): AiActionApplyResult

    fun undoLastAiAction(
        planId: String,
        undoToken: String,
    ): AiUndoResult
}

enum class AddPlaceResult {
    ADDED,
    ALREADY_EXISTS,
    MISSING_LOCATION,
    PLAN_NOT_FOUND,
}

sealed class AddPlaceTarget {
    data class Day(val dayIndex: Int) : AddPlaceTarget()
    data object Unplanned : AddPlaceTarget()
}

enum class MoveDirection {
    UP,
    DOWN,
}

data class AiActionApplyResult(
    val success: Boolean,
    val message: String,
    val undoToken: String? = null,
    val affectedDayIndexes: List<Int> = emptyList(),
)

data class AiUndoResult(
    val success: Boolean,
    val message: String,
)

open class InMemoryTravelPlanRepository(
    initialPlans: List<TravelPlan> = emptyList(),
    private val onPlansChanged: (List<TravelPlan>) -> Unit = {},
    seedDefaultPlanWhenEmpty: Boolean = true,
) : TravelPlanRepository {
    private var lastAiUndoSnapshot: AiUndoSnapshot? = null

    private val _plans = MutableStateFlow(
        sanitizePlans(initialPlans).let { plans ->
            if (plans.isEmpty() && seedDefaultPlanWhenEmpty) listOf(defaultInitialPlan()) else plans
        },
    )
    override val plans: StateFlow<List<TravelPlan>> = _plans.asStateFlow()

    override fun createPlan(
        destination: String,
        dateRange: String,
        preferences: List<String>,
        dayCount: Int?,
    ): TravelPlan {
        val cleanDestination = destination.trim().ifBlank { "未命名目的地" }
        val now = System.currentTimeMillis()
        val plan = TravelPlan(
            id = UUID.randomUUID().toString(),
            title = "${cleanDestination}旅行",
            destination = cleanDestination,
            dateRange = dateRange.trim().ifBlank { "未设置日期" },
            dayCount = dayCount?.coerceIn(1, 10) ?: estimateDayCount(dateRange),
            preferences = preferences.ifEmpty { listOf("轻松随心") },
            createdAt = now,
            revision = 1L,
            updatedAt = now,
        )

        _plans.update { current -> listOf(plan) + current }
        persistCurrentPlans()
        return plan
    }

    override fun importGeneratedPlan(generated: AiPlanGenerationResponse): TravelPlan {
        val now = System.currentTimeMillis()
        val planId = UUID.randomUUID().toString()
        val days = generated.days
            .sortedBy { it.dayIndex }
            .map { generatedDay ->
                val dayId = "$planId-day-${generatedDay.dayIndex}"
                PlanDay(
                    id = dayId,
                    dayIndex = generatedDay.dayIndex,
                    title = generatedDay.title,
                    items = generatedDay.places.mapIndexed { index, place ->
                        PlanItem(
                            id = place.id,
                            source = place.source,
                            sourcePoiId = place.sourcePoiId,
                            name = place.name,
                            category = place.category,
                            categoryCode = place.categoryCode,
                            typeName = place.typeName,
                            typeCode = place.typeCode,
                            address = place.address,
                            provinceName = place.provinceName,
                            cityName = place.cityName,
                            districtName = place.districtName,
                            adCode = place.adCode,
                            cityCode = place.cityCode,
                            latitude = place.latitude,
                            longitude = place.longitude,
                            dayId = dayId,
                            dayIndex = generatedDay.dayIndex,
                            visitOrder = index + 1,
                            note = place.note,
                            suggestedStart = place.suggestedStart,
                            suggestedEnd = place.suggestedEnd,
                            transportModeToNext = generatedDay.transfers
                                .firstOrNull { it.originPlaceId == place.id }
                                ?.mode
                                ?: "walking",
                            thumbnailUrl = place.thumbnailUrl,
                            imageUrls = place.imageUrls,
                            phone = place.phone,
                            rating = place.rating,
                            costAverage = place.costAverage,
                            businessArea = place.businessArea,
                            openingHoursToday = place.openingHoursToday,
                            openingHoursWeek = place.openingHoursWeek,
                            scheduleVerified = place.scheduleVerified,
                        )
                    },
                )
            }
        val plan = TravelPlan(
            id = planId,
            title = generated.title,
            destination = generated.destination,
            dateRange = generated.dateRange,
            dayCount = generated.dayCount,
            preferences = generated.preferences.ifEmpty { listOf("智能规划") },
            createdAt = now,
            revision = 1L,
            updatedAt = now,
            days = days,
        )
        _plans.update { current -> listOf(plan) + current }
        persistCurrentPlans()
        return plan
    }

    override fun getPlan(planId: String): TravelPlan? {
        return _plans.value.firstOrNull { it.id == planId }
    }

    override fun deletePlan(planId: String): Boolean {
        var deleted = false
        _plans.update { current ->
            val updated = current.filterNot { it.id == planId }
            deleted = updated.size != current.size
            updated
        }
        if (deleted) {
            lastAiUndoSnapshot = lastAiUndoSnapshot?.takeUnless { it.planId == planId }
            persistCurrentPlans()
        }
        return deleted
    }

    override fun addPlaceToPlan(
        planId: String,
        place: PlaceSummary,
        target: AddPlaceTarget,
    ): AddPlaceResult {
        if (target is AddPlaceTarget.Day && (place.latitude == null || place.longitude == null)) {
            return AddPlaceResult.MISSING_LOCATION
        }

        var result = AddPlaceResult.PLAN_NOT_FOUND
        var changed = false
        _plans.update { current ->
            current.map { plan ->
                if (plan.id != planId) return@map plan
                result = AddPlaceResult.ADDED

                val days = ensureDays(plan)
                if (plan.allItems().any { it.sourcePoiId == place.sourcePoiId }) {
                    result = AddPlaceResult.ALREADY_EXISTS
                    return@map plan
                }

                changed = true
                when (target) {
                    is AddPlaceTarget.Day -> {
                        val safeDayIndex = target.dayIndex.coerceIn(1, days.size)
                        val targetDay = days.first { it.dayIndex == safeDayIndex }
                        val item = place.toPlanItem(
                            dayId = targetDay.id,
                            dayIndex = targetDay.dayIndex,
                            visitOrder = targetDay.items.orEmpty().size + 1,
                        )
                        val updatedDays = days.map { day ->
                            if (day.dayIndex == safeDayIndex) {
                                day.copy(items = normalizeOrders(day.items.orEmpty() + item))
                            } else {
                                day
                            }
                        }
                        plan.copy(days = updatedDays).nextRevision()
                    }

                    AddPlaceTarget.Unplanned -> {
                        val item = place.toPlanItem(
                            dayId = UNPLANNED_DAY_ID,
                            dayIndex = UNPLANNED_DAY_INDEX,
                            visitOrder = plan.unplannedItems.orEmpty().size + 1,
                        )
                        plan.copy(
                            days = days,
                            unplannedItems = normalizeOrders(plan.unplannedItems.orEmpty() + item).map {
                                it.copy(dayId = UNPLANNED_DAY_ID, dayIndex = UNPLANNED_DAY_INDEX)
                            },
                        ).nextRevision()
                    }
                }
            }
        }

        if (changed) persistCurrentPlans()
        return result
    }

    override fun moveUnplannedItemToDay(
        planId: String,
        itemId: String,
        dayIndex: Int,
    ): AddPlaceResult {
        var result = AddPlaceResult.PLAN_NOT_FOUND
        var changed = false
        _plans.update { current ->
            current.map { plan ->
                if (plan.id != planId) return@map plan

                val sourceItem = plan.unplannedItems.orEmpty().firstOrNull { it.id == itemId }
                    ?: return@map plan
                if (sourceItem.latitude == null || sourceItem.longitude == null) {
                    result = AddPlaceResult.MISSING_LOCATION
                    return@map plan
                }

                val days = ensureDays(plan)
                val safeDayIndex = dayIndex.coerceIn(1, days.size)
                val targetDay = days.first { it.dayIndex == safeDayIndex }
                val movedItem = sourceItem.copy(
                    dayId = targetDay.id,
                    dayIndex = targetDay.dayIndex,
                    visitOrder = targetDay.items.orEmpty().size + 1,
                )
                val updatedDays = days.map { day ->
                    if (day.dayIndex == safeDayIndex) {
                        day.copy(items = normalizeOrders(day.items.orEmpty() + movedItem))
                    } else {
                        day
                    }
                }

                result = AddPlaceResult.ADDED
                changed = true
                plan.copy(
                    days = updatedDays,
                    unplannedItems = normalizeOrders(
                        plan.unplannedItems.orEmpty().filterNot { it.id == itemId },
                    ).map {
                        it.copy(dayId = UNPLANNED_DAY_ID, dayIndex = UNPLANNED_DAY_INDEX)
                    },
                ).nextRevision()
            }
        }

        if (changed) persistCurrentPlans()
        return result
    }

    override fun movePlanItem(
        planId: String,
        dayIndex: Int,
        itemId: String,
        direction: MoveDirection,
    ) {
        var changed = false
        _plans.update { current ->
            current.map { plan ->
                if (plan.id != planId) return@map plan
                val updatedDays = ensureDays(plan).map { day ->
                    if (day.dayIndex != dayIndex) {
                        day
                    } else {
                        day.copy(items = moveItem(day.items.orEmpty(), itemId, direction))
                    }
                }
                if (updatedDays == plan.days) {
                    plan
                } else {
                    changed = true
                    plan.copy(days = updatedDays).nextRevision()
                }
            }
        }

        if (changed) persistCurrentPlans()
    }

    override fun applyOptimizedOrder(
        planId: String,
        dayIndex: Int,
        orderedPlaceIds: List<String>,
    ) {
        var changed = false
        _plans.update { current ->
            current.map { plan ->
                if (plan.id != planId) return@map plan
                val updatedDays = ensureDays(plan).map { day ->
                    if (day.dayIndex != dayIndex) {
                        day
                    } else {
                        val items = day.items.orEmpty()
                        val byId = items.associateBy { it.id }
                        val ordered = orderedPlaceIds.mapNotNull(byId::get)
                        val remaining = items.filterNot { it.id in orderedPlaceIds }
                        day.copy(items = normalizeOrders(ordered + remaining))
                    }
                }
                if (updatedDays == plan.days) {
                    plan
                } else {
                    changed = true
                    plan.copy(days = updatedDays).nextRevision()
                }
            }
        }

        if (changed) persistCurrentPlans()
    }

    override fun applyAiSuggestedActions(
        planId: String,
        expectedRevision: Long?,
        actions: List<AiSuggestedAction>,
    ): AiActionApplyResult {
        if (actions.isEmpty()) {
            return AiActionApplyResult(false, "没有可应用的 AI 建议。")
        }

        var result = AiActionApplyResult(false, "计划不存在。")
        var changed = false
        val undoToken = UUID.randomUUID().toString()

        _plans.update { current ->
            current.map { plan ->
                if (plan.id != planId) return@map plan
                if (expectedRevision != null && plan.revision != expectedRevision) {
                    result = AiActionApplyResult(false, "计划已经发生变化，请重新生成 AI 建议。")
                    return@map plan
                }

                val applyResult = applyActionsToPlan(plan, actions)
                if (!applyResult.success || applyResult.plan == null) {
                    result = AiActionApplyResult(false, applyResult.message)
                    return@map plan
                }

                changed = true
                val updatedPlan = applyResult.plan.nextRevision()
                lastAiUndoSnapshot = AiUndoSnapshot(
                    token = undoToken,
                    planId = planId,
                    beforePlan = plan,
                    afterRevision = updatedPlan.revision,
                )
                result = AiActionApplyResult(
                    success = true,
                    message = "已应用 AI 建议，受影响的 DAY 会重新计算路线。",
                    undoToken = undoToken,
                    affectedDayIndexes = applyResult.affectedDayIndexes,
                )
                updatedPlan
            }
        }

        if (changed) persistCurrentPlans()
        return result
    }

    override fun undoLastAiAction(planId: String, undoToken: String): AiUndoResult {
        val snapshot = lastAiUndoSnapshot
            ?: return AiUndoResult(false, "当前没有可撤销的 AI 修改。")
        if (snapshot.planId != planId || snapshot.token != undoToken) {
            return AiUndoResult(false, "撤销凭证已失效。")
        }

        var undone = false
        var result = AiUndoResult(false, "计划不存在。")
        _plans.update { current ->
            current.map { plan ->
                if (plan.id != planId) return@map plan
                if (plan.revision != snapshot.afterRevision) {
                    result = AiUndoResult(false, "计划已经被继续修改，不能再撤销这次 AI 调整。")
                    return@map plan
                }
                undone = true
                result = AiUndoResult(true, "已撤销最近一次 AI 调整。")
                snapshot.beforePlan.nextRevision()
            }
        }

        if (undone) {
            lastAiUndoSnapshot = null
            persistCurrentPlans()
        }
        return result
    }

    private fun applyActionsToPlan(
        originalPlan: TravelPlan,
        actions: List<AiSuggestedAction>,
    ): InternalApplyResult {
        var workingPlan = originalPlan.copy(days = ensureDays(originalPlan))
        val affectedDays = linkedSetOf<Int>()
        val touchedPlaces = mutableSetOf<String>()

        actions.forEach { action ->
            if (!touchedPlaces.add(action.placeItemId)) {
                return InternalApplyResult(false, "同一个地点在本轮建议中被重复修改。")
            }

            val located = workingPlan.findItem(action.placeItemId)
                ?: return InternalApplyResult(false, "地点不在当前计划中：${action.placeItemId}")

            when (action.type) {
                "MOVE_PLACE_TO_DAY", "ASSIGN_UNPLANNED_PLACE", "REORDER_PLACE" -> {
                    val targetDayIndex = action.toDayIndex
                        ?: return InternalApplyResult(false, "AI 建议缺少目标 DAY。")
                    val targetDay = workingPlan.days.firstOrNull { it.dayIndex == targetDayIndex }
                        ?: return InternalApplyResult(false, "目标 DAY 不存在：DAY $targetDayIndex")
                    if (located.item.latitude == null || located.item.longitude == null) {
                        return InternalApplyResult(false, "地点缺少坐标，不能加入路线 DAY：${located.item.name}")
                    }
                    if (action.type == "ASSIGN_UNPLANNED_PLACE" && located.dayIndex != UNPLANNED_DAY_INDEX) {
                        return InternalApplyResult(false, "该地点不是待规划地点：${located.item.name}")
                    }

                    workingPlan = workingPlan.removeItem(action.placeItemId)
                    workingPlan = workingPlan.insertIntoDay(
                        item = located.item.copy(dayId = targetDay.id, dayIndex = targetDay.dayIndex),
                        dayIndex = targetDay.dayIndex,
                        position = action.toPosition ?: Int.MAX_VALUE,
                    )
                    located.dayIndex.takeIf { it > 0 }?.let(affectedDays::add)
                    affectedDays.add(targetDay.dayIndex)
                }

                "MOVE_TO_UNPLANNED" -> {
                    workingPlan = workingPlan.removeItem(action.placeItemId)
                    workingPlan = workingPlan.copy(
                        unplannedItems = normalizeOrders(
                            workingPlan.unplannedItems.orEmpty() + located.item.copy(
                                dayId = UNPLANNED_DAY_ID,
                                dayIndex = UNPLANNED_DAY_INDEX,
                            ),
                        ).map { it.copy(dayId = UNPLANNED_DAY_ID, dayIndex = UNPLANNED_DAY_INDEX) },
                    )
                    located.dayIndex.takeIf { it > 0 }?.let(affectedDays::add)
                }

                else -> return InternalApplyResult(false, "不支持的 AI 建议类型：${action.type}")
            }
        }

        return InternalApplyResult(
            success = true,
            message = "OK",
            plan = sanitizePlans(listOf(workingPlan)).first(),
            affectedDayIndexes = affectedDays.toList(),
        )
    }

    private fun persistCurrentPlans() {
        onPlansChanged(sanitizePlans(_plans.value))
    }

    private fun estimateDayCount(dateRange: String): Int {
        val compact = dateRange.replace(" ", "")
        val dayMatch = Regex("(\\d+)天").find(compact)
        if (dayMatch != null) {
            return dayMatch.groupValues[1].toIntOrNull()?.coerceIn(1, 15) ?: 1
        }
        return when {
            compact.isBlank() -> 1
            compact.contains("三") || compact.contains("3") -> 3
            compact.contains("四") || compact.contains("4") -> 4
            compact.contains("五") || compact.contains("5") -> 5
            else -> 2
        }
    }

    private fun ensureDays(plan: TravelPlan): List<PlanDay> {
        val existingDays = plan.days.orEmpty()
        if (existingDays.isNotEmpty()) {
            return existingDays.map { day ->
                day.copy(items = normalizeOrders(day.items.orEmpty()))
            }
        }

        return List(plan.dayCount.coerceAtLeast(1)) { index ->
            PlanDay(
                id = "${plan.id}-day-${index + 1}",
                dayIndex = index + 1,
                title = "DAY ${index + 1}",
            )
        }
    }

    private fun PlaceSummary.toPlanItem(
        dayId: String,
        dayIndex: Int,
        visitOrder: Int,
    ): PlanItem {
        return PlanItem(
            id = id,
            source = source,
            sourcePoiId = sourcePoiId,
            name = name,
            category = category,
            categoryCode = categoryCode,
            typeName = typeName,
            typeCode = typeCode,
            address = address,
            provinceName = provinceName,
            cityName = cityName,
            districtName = districtName,
            adCode = adCode,
            cityCode = cityCode,
            latitude = latitude,
            longitude = longitude,
            dayId = dayId,
            dayIndex = dayIndex,
            visitOrder = visitOrder,
            thumbnailUrl = displayCoverImageUrl,
            imageUrls = displayImageUrls,
            phone = phone,
            rating = rating,
            costAverage = costAverage,
            businessArea = businessArea,
            openingHoursToday = openingHoursToday,
            openingHoursWeek = openingHoursWeek,
        )
    }

    private fun TravelPlan.allItems(): List<PlanItem> {
        return days.orEmpty().flatMap { it.items.orEmpty() } + unplannedItems.orEmpty()
    }
}

class PersistentTravelPlanRepository private constructor(
    localStore: TravelPlanLocalStore,
) : InMemoryTravelPlanRepository(
    initialPlans = localStore.loadPlans(),
    onPlansChanged = localStore::savePlans,
    seedDefaultPlanWhenEmpty = !localStore.hasSavedPlans(),
) {
    constructor(context: Context) : this(TravelPlanLocalStore(context.applicationContext))
}

private class TravelPlanLocalStore(
    context: Context,
) {
    private val preferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val gson = Gson()
    private val planListType = object : TypeToken<List<TravelPlan>>() {}.type

    fun hasSavedPlans(): Boolean = preferences.contains(KEY_PLANS)

    fun loadPlans(): List<TravelPlan> {
        val json = preferences.getString(KEY_PLANS, null) ?: return emptyList()
        return runCatching {
            val plans = gson.fromJson<List<TravelPlan>>(json, planListType).orEmpty()
            sanitizePlans(plans)
        }.getOrElse {
            emptyList()
        }
    }

    fun savePlans(plans: List<TravelPlan>) {
        preferences.edit()
            .putString(KEY_PLANS, gson.toJson(sanitizePlans(plans)))
            .apply()
    }

    private companion object {
        const val PREFS_NAME = "ai_travel_plans"
        const val KEY_PLANS = "plans_json"
    }
}

fun PlanItem.toRoutePlace(): RoutePlace? {
    val lat = latitude ?: return null
    val lng = longitude ?: return null
    return RoutePlace(
        id = id,
        name = name,
        latitude = lat,
        longitude = lng,
        address = address,
        cityName = cityName,
        adCode = adCode,
        cityCode = cityCode,
    )
}

private fun defaultInitialPlan(): TravelPlan {
    val now = System.currentTimeMillis()
    return TravelPlan(
        id = "chengdu-demo",
        title = "成都市旅行",
        destination = "成都",
        dateRange = "7月10日 - 7月13日",
        dayCount = 4,
        preferences = listOf("美食打卡", "自然风光", "citywalk"),
        createdAt = now,
        revision = 1L,
        updatedAt = now,
    )
}

private fun sanitizePlans(plans: List<TravelPlan>): List<TravelPlan> {
    return plans.map { plan ->
        val safeDays = plan.days.orEmpty().ifEmpty {
            List(plan.dayCount.coerceAtLeast(1)) { index ->
                PlanDay(
                    id = "${plan.id}-day-${index + 1}",
                    dayIndex = index + 1,
                    title = "DAY ${index + 1}",
                )
            }
        }.map { day ->
            day.copy(items = normalizeOrders(day.items.orEmpty()))
        }

        plan.copy(
            days = safeDays,
            revision = plan.revision.takeIf { it > 0L } ?: 1L,
            updatedAt = plan.updatedAt.takeIf { it > 0L } ?: plan.createdAt,
            unplannedItems = normalizeOrders(plan.unplannedItems.orEmpty()).map {
                it.copy(dayId = UNPLANNED_DAY_ID, dayIndex = UNPLANNED_DAY_INDEX)
            },
        )
    }
}

private fun normalizeOrders(items: List<PlanItem>): List<PlanItem> {
    return items.mapIndexed { index, item ->
        item.copy(visitOrder = index + 1)
    }
}

private fun moveItem(
    items: List<PlanItem>,
    itemId: String,
    direction: MoveDirection,
): List<PlanItem> {
    val mutable = items.toMutableList()
    val index = mutable.indexOfFirst { it.id == itemId }
    if (index == -1) return items
    val targetIndex = when (direction) {
        MoveDirection.UP -> index - 1
        MoveDirection.DOWN -> index + 1
    }
    if (targetIndex !in mutable.indices) return items
    val item = mutable.removeAt(index)
    mutable.add(targetIndex, item)
    return normalizeOrders(mutable)
}

private data class AiUndoSnapshot(
    val token: String,
    val planId: String,
    val beforePlan: TravelPlan,
    val afterRevision: Long,
)

private data class InternalApplyResult(
    val success: Boolean,
    val message: String,
    val plan: TravelPlan? = null,
    val affectedDayIndexes: List<Int> = emptyList(),
)

private data class LocatedPlanItem(
    val item: PlanItem,
    val dayIndex: Int,
)

private fun TravelPlan.nextRevision(): TravelPlan {
    return copy(
        revision = (revision.takeIf { it > 0L } ?: 1L) + 1L,
        updatedAt = System.currentTimeMillis(),
    )
}

private fun TravelPlan.findItem(itemId: String): LocatedPlanItem? {
    days.orEmpty().forEach { day ->
        day.items.orEmpty().firstOrNull { it.id == itemId }?.let {
            return LocatedPlanItem(it, day.dayIndex)
        }
    }
    unplannedItems.orEmpty().firstOrNull { it.id == itemId }?.let {
        return LocatedPlanItem(it, UNPLANNED_DAY_INDEX)
    }
    return null
}

private fun TravelPlan.removeItem(itemId: String): TravelPlan {
    return copy(
        days = days.orEmpty().map { day ->
            day.copy(items = normalizeOrders(day.items.orEmpty().filterNot { it.id == itemId }))
        },
        unplannedItems = normalizeOrders(unplannedItems.orEmpty().filterNot { it.id == itemId }).map {
            it.copy(dayId = UNPLANNED_DAY_ID, dayIndex = UNPLANNED_DAY_INDEX)
        },
    )
}

private fun TravelPlan.insertIntoDay(
    item: PlanItem,
    dayIndex: Int,
    position: Int,
): TravelPlan {
    val updatedDays = days.orEmpty().map { day ->
        if (day.dayIndex != dayIndex) {
            day
        } else {
            val mutable = day.items.orEmpty().toMutableList()
            val targetIndex = (position - 1).coerceIn(0, mutable.size)
            mutable.add(targetIndex, item.copy(dayId = day.id, dayIndex = day.dayIndex))
            day.copy(items = normalizeOrders(mutable))
        }
    }
    return copy(days = updatedDays)
}
