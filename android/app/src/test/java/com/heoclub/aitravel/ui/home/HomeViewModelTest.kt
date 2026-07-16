package com.heoclub.aitravel.ui.home

import com.heoclub.aitravel.data.model.HealthResponse
import com.heoclub.aitravel.data.repository.HealthRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun initLoadsHealthSuccessfully() = runTest {
        val viewModel = HomeViewModel(
            healthRepository = FakeHealthRepository(
                Result.success(
                    HealthResponse(
                        code = 200,
                        message = "AI Travel backend is running",
                        status = "ok",
                    ),
                ),
            ),
        )

        assertEquals(HomeUiState.Loading, viewModel.uiState.value)
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(
            HomeUiState.Success("AI Travel backend is running"),
            viewModel.uiState.value,
        )
    }

    @Test
    fun initShowsReadableErrorWhenHealthFails() = runTest {
        val viewModel = HomeViewModel(
            healthRepository = FakeHealthRepository(
                Result.failure(IllegalStateException("暂时无法连接后端")),
            ),
        )

        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(
            HomeUiState.Error("暂时无法连接后端"),
            viewModel.uiState.value,
        )
    }

    @Test
    fun retryReturnsToLoadingThenSuccess() = runTest {
        val repository = QueueHealthRepository(
            listOf(
                Result.failure(IllegalStateException("暂时无法连接后端")),
                Result.success(
                    HealthResponse(
                        code = 200,
                        message = "AI Travel backend is running",
                        status = "ok",
                    ),
                ),
            ),
        )
        val viewModel = HomeViewModel(repository)

        dispatcher.scheduler.advanceUntilIdle()
        assertTrue(viewModel.uiState.value is HomeUiState.Error)

        viewModel.refreshHealth()
        assertEquals(HomeUiState.Loading, viewModel.uiState.value)
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(
            HomeUiState.Success("AI Travel backend is running"),
            viewModel.uiState.value,
        )
    }
}

private class FakeHealthRepository(
    private val result: Result<HealthResponse>,
) : HealthRepository {
    override suspend fun checkHealth(): Result<HealthResponse> = result
}

private class QueueHealthRepository(
    results: List<Result<HealthResponse>>,
) : HealthRepository {
    private val queue = ArrayDeque(results)

    override suspend fun checkHealth(): Result<HealthResponse> {
        return queue.removeFirst()
    }
}

